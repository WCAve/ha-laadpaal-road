"""Laadwens: houdt een laadpaal in de gaten en stuurt meldingen.

Werking per laadpaal (config entry):

* Laadwens aan en er is een socket vrij (eventueel pas na X minuten vrij):
  melding "is vrij". Was de paal al vrij op het moment van aanzetten, dan
  komt de melding meteen.
* Na zo'n melding volgen we de paal nog FOLLOW_UP_WINDOW lang. Raakt hij in
  die tijd weer bezet, dan komt er een melding "weer bezet" (die de eerste
  melding op je telefoon vervangt). Is de ingestelde persoon op dat moment
  bij de paal, dan ben jij het zelf en komt er geen melding.
* De laadwens gaat uit: na de melding (optie), na X uur (optie), via de
  "Stop" knop in de melding, of als jij bij de paal aankomt en hem bezet.
* Meerdere palen tegelijk (optie, standaard aan): de eerste paal die vrij
  komt meldt zich, en de laadwensen op de andere palen gaan dan uit. Zo krijg
  je één melding voor "maakt niet uit welke, als er maar plek is".
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import (
    ACTION_STOP_PREFIX,
    ARRIVAL_RADIUS_M,
    CONF_ANDROID_AUTO,
    CONF_DISARM_AFTER_NOTIFY,
    CONF_DISARM_OTHERS,
    CONF_EXPIRE_HOURS,
    CONF_MIN_FREE_MINUTES,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_WHEN_TAKEN,
    CONF_PERSON,
    DEFAULT_OPTIONS,
    DOMAIN,
    FOLLOW_UP_WINDOW,
    GROUP_ARM_GRACE,
    NOTIFY_CHANNEL,
    TARGET_PERSISTENT,
)
from .data import coordinates, evses, free_count
from .tariff import evaluate

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import RoadDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

EVENT_MOBILE_APP_ACTION = "mobile_app_notification_action"
# hass.data sleutel: wanneer een "eerste vrije paal"-melding is verstuurd.
DATA_GROUP_NOTIFIED_AT = f"{DOMAIN}_group_notified_at"


class RoadWatcher:
    """Laadwens-logica voor één laadpaal."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: RoadDataUpdateCoordinator,
    ) -> None:
        """Initialiseer de watcher (nog niet actief, zie async_start)."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator

        self.armed = False
        self.expires_at: datetime | None = None

        self._free_since: datetime | None = None
        self._notified = False
        self._follow_until: datetime | None = None
        self._unsub_recheck: CALLBACK_TYPE | None = None
        self._unsub_expire: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ setup

    @callback
    def async_start(self) -> None:
        """Begin met luisteren naar nieuwe data en meldingsknoppen."""
        self.entry.async_on_unload(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        self.entry.async_on_unload(
            self.hass.bus.async_listen(
                EVENT_MOBILE_APP_ACTION, self._handle_notification_action
            )
        )
        self.entry.async_on_unload(self._cancel_timers)

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Laat een entiteit (de switch) weten wanneer de laadwens verandert."""
        self._listeners.append(update)

        @callback
        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    # --------------------------------------------------------------- helpers

    @property
    def name(self) -> str:
        """Naam van de laadpaal zoals de gebruiker hem noemde."""
        return self.entry.title

    @property
    def options(self) -> dict[str, Any]:
        """Actuele opties, aangevuld met standaardwaarden."""
        return {**DEFAULT_OPTIONS, **self.entry.options}

    @property
    def free(self) -> int | None:
        """Aantal vrije sockets, of None als de data nu onbetrouwbaar is."""
        if not self.coordinator.last_update_success or not self.coordinator.data:
            return None
        return free_count(self.coordinator.data)

    @property
    def maps_url(self) -> str | None:
        """Route naar de paal (opent Google Maps of de browser)."""
        coords = coordinates(self.coordinator.data)
        if coords is None:
            return None
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&destination={coords[0]},{coords[1]}"
        )

    def _person_at_charger(self) -> bool:
        """Is de ingestelde persoon binnen ARRIVAL_RADIUS_M van de paal?"""
        person = self.options.get(CONF_PERSON)
        coords = coordinates(self.coordinator.data)
        if not person or coords is None:
            return False
        state = self.hass.states.get(person)
        if state is None:
            return False
        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        if lat is None or lon is None:
            return False
        meters = distance(lat, lon, coords[0], coords[1])
        return meters is not None and meters <= ARRIVAL_RADIUS_M

    def _other_watchers(self) -> list[RoadWatcher]:
        """Watchers van de andere geladen laadpalen."""
        others: list[RoadWatcher] = []
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            data = getattr(entry, "runtime_data", None)
            watcher = getattr(data, "watcher", None)
            if watcher is not None and watcher is not self:
                others.append(watcher)
        return others

    @callback
    def _update_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def _cancel_recheck(self) -> None:
        if self._unsub_recheck:
            self._unsub_recheck()
            self._unsub_recheck = None

    @callback
    def _cancel_expire(self) -> None:
        if self._unsub_expire:
            self._unsub_expire()
            self._unsub_expire = None

    @callback
    def _cancel_timers(self) -> None:
        self._cancel_recheck()
        self._cancel_expire()

    @callback
    def _schedule_expiry(self) -> None:
        self._cancel_expire()
        if self.expires_at is None:
            return
        delay = max((self.expires_at - dt_util.utcnow()).total_seconds(), 0)
        self._unsub_expire = async_call_later(self.hass, delay, self._handle_expired)

    def _run(self, coro: Coroutine[Any, Any, Any], name: str) -> None:
        self.entry.async_create_background_task(self.hass, coro, name)

    # ---------------------------------------------------------- arm / disarm

    @callback
    def async_arm(self) -> None:
        """Zet de laadwens aan."""
        if self.armed:
            return
        # Net een "eerste vrije paal"-melding gehad (bv. alle bellen tegelijk
        # aangezet en er was er al één vrij)? Dan is deze wens al vervuld.
        group_at: datetime | None = self.hass.data.get(DATA_GROUP_NOTIFIED_AT)
        if (
            self.options[CONF_DISARM_OTHERS]
            and group_at is not None
            and dt_util.utcnow() - group_at <= GROUP_ARM_GRACE
        ):
            _LOGGER.debug(
                "%s: andere paal is net vrij gemeld, niet aangezet", self.name
            )
            self._update_listeners()
            return
        self.armed = True
        self._notified = False
        self._free_since = None
        hours = float(self.options[CONF_EXPIRE_HOURS] or 0)
        self.expires_at = (
            dt_util.utcnow() + timedelta(hours=hours) if hours > 0 else None
        )
        self._schedule_expiry()
        self._update_listeners()

        # Al vrij? Dan meteen melden, zonder "minimaal X minuten vrij" af te wachten.
        if self.free:
            self._notify_free()

    @callback
    def async_disarm(self, *, stop_follow_up: bool = False) -> None:
        """Zet de laadwens uit."""
        self._cancel_timers()
        self._free_since = None
        if stop_follow_up:
            self._follow_until = None
            self._notified = False
        if self.armed:
            self.armed = False
            self.expires_at = None
            self._update_listeners()

    @callback
    def async_restore(self, expires_at: datetime | None) -> None:
        """Herstel een actieve laadwens na een herstart (zonder te melden)."""
        if self.armed:
            return
        if expires_at is not None and expires_at <= dt_util.utcnow():
            return
        self.armed = True
        self.expires_at = expires_at
        # Was de paal al vrij, dan is daar vóór de herstart al over gemeld.
        self._notified = bool(self.free)
        self._schedule_expiry()
        self._update_listeners()

    # ------------------------------------------------------------- triggers

    @callback
    def _handle_coordinator_update(self) -> None:
        """Nieuwe data binnen: bepaal of er een melding moet komen."""
        free = self.free
        if free is None:
            return
        now = dt_util.utcnow()
        if self._follow_until and now > self._follow_until:
            self._follow_until = None

        if free == 0:
            self._free_since = None
            self._cancel_recheck()
            if self._notified or self._follow_until:
                if self._person_at_charger():
                    # Jij bent degene die de paal nu bezet: klaar.
                    _LOGGER.debug("%s: bezet door jezelf, laadwens uit", self.name)
                    self.async_disarm(stop_follow_up=True)
                    return
                if self._follow_until:
                    self._notify_taken()
                    self._follow_until = None
            self._notified = False
            return

        if not self.armed or self._notified:
            return

        if self._free_since is None:
            self._free_since = now
        min_free = timedelta(minutes=float(self.options[CONF_MIN_FREE_MINUTES] or 0))
        remaining = (self._free_since + min_free - now).total_seconds()
        if remaining > 0:
            if self._unsub_recheck is None:
                self._unsub_recheck = async_call_later(
                    self.hass, remaining, self._handle_recheck
                )
            return
        self._notify_free()

    @callback
    def _handle_recheck(self, _now: datetime) -> None:
        self._unsub_recheck = None
        self._handle_coordinator_update()

    @callback
    def _handle_expired(self, _now: datetime) -> None:
        self._unsub_expire = None
        if not self.armed:
            return
        hours = self.options[CONF_EXPIRE_HOURS]
        self.async_disarm()
        self._run(
            self.async_send(
                "⏰ Laadwens verlopen",
                f"{self.name}: er is in {_hours(hours)} geen plek vrijgekomen.",
                stop_button=False,
                car=True,
            ),
            f"{DOMAIN} expired notification",
        )

    @callback
    def _handle_notification_action(self, event: Event) -> None:
        if event.data.get("action") == f"{ACTION_STOP_PREFIX}{self.entry.entry_id}":
            self.async_disarm(stop_follow_up=True)

    # --------------------------------------------------------- notifications

    @callback
    def _notify_free(self) -> None:
        self._notified = True
        self._cancel_recheck()
        if self.options[CONF_NOTIFY_WHEN_TAKEN]:
            self._follow_until = dt_util.utcnow() + FOLLOW_UP_WINDOW
        title, message = self.free_message()

        if self.options[CONF_DISARM_OTHERS]:
            self.hass.data[DATA_GROUP_NOTIFIED_AT] = dt_util.utcnow()
            stopped = [w for w in self._other_watchers() if w.armed]
            for other in stopped:
                other.async_disarm()
            if stopped:
                names = ", ".join(sorted(w.name for w in stopped))
                message += f"\nLaadwens uitgezet voor: {names}."
        self._run(
            self.async_send(title, message, stop_button=True, car=True),
            f"{DOMAIN} free notification",
        )
        if self.options[CONF_DISARM_AFTER_NOTIFY]:
            self.async_disarm()

    @callback
    def _notify_taken(self) -> None:
        message = "Er is geen socket meer vrij."
        if self.armed:
            message += " Je krijgt een melding zodra er weer plek is."
        self._run(
            self.async_send(
                f"⛔ {self.name} is weer bezet",
                message,
                stop_button=self.armed,
                car=True,
            ),
            f"{DOMAIN} taken notification",
        )

    def free_message(self) -> tuple[str, str]:
        """Titel en tekst voor een "vrij" melding."""
        data = self.coordinator.data
        message = f"{free_count(data)} van de {len(evses(data))} sockets vrij"
        tariff_now = evaluate(data)
        if tariff_now.energy is not None:
            message += f" · €{tariff_now.energy:.2f}/kWh".replace(".", ",")
            if tariff_now.start_fee > 0:
                message += f" + €{tariff_now.start_fee:.2f} start".replace(".", ",")
        if tariff_now.blocking_fee:
            message += f" · {tariff_now.blocking_fee.text}"
        return f"🔌 {self.name} is vrij", message

    async def async_send(
        self,
        title: str,
        message: str,
        *,
        stop_button: bool,
        raise_on_error: bool = False,
        car: bool = False,
        tag_suffix: str = "",
    ) -> None:
        """Stuur een melding naar alle ingestelde doelen."""
        targets: list[str] = self.options[CONF_NOTIFY_TARGETS]
        if not targets:
            if raise_on_error:
                raise HomeAssistantError(
                    f"Er zijn nog geen meldingsdoelen ingesteld voor {self.name}. "
                    "Kies ze via Instellingen > Apparaten & diensten > "
                    "EV Location Radar > Configureren."
                )
            _LOGGER.debug("%s: geen meldingsdoelen ingesteld", self.name)
            return

        tag = f"{DOMAIN}_{self.entry.entry_id}{tag_suffix}"
        url = self.maps_url
        errors: list[str] = []

        for target in targets:
            try:
                if target == TARGET_PERSISTENT:
                    text = f"{message}\n\n[Navigeer]({url})" if url else message
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {"title": title, "message": text, "notification_id": tag},
                        blocking=True,
                    )
                    continue

                service_data: dict[str, Any] = {"title": title, "message": message}
                if target.startswith("mobile_app_"):
                    extra: dict[str, Any] = {"tag": tag, "group": DOMAIN}
                    if car and self.options[CONF_ANDROID_AUTO]:
                        # Android Auto toont alleen meldingen met car_ui; een
                        # eigen kanaal met hoge prioriteit laat hem opduiken.
                        extra["car_ui"] = True
                        extra["channel"] = NOTIFY_CHANNEL
                        extra["importance"] = "high"
                    actions: list[dict[str, str]] = []
                    if url:
                        extra["url"] = url  # iOS: tik op de melding
                        extra["clickAction"] = url  # Android: tik op de melding
                        actions.append(
                            {"action": "URI", "title": "Navigeer", "uri": url}
                        )
                    if stop_button:
                        actions.append(
                            {
                                "action": f"{ACTION_STOP_PREFIX}{self.entry.entry_id}",
                                "title": "Stop",
                            }
                        )
                    if actions:
                        extra["actions"] = actions
                    service_data["data"] = extra

                await self.hass.services.async_call(
                    "notify", target, service_data, blocking=True
                )
            except (HomeAssistantError, vol.Invalid) as err:
                _LOGGER.warning(
                    "%s: melding naar %s mislukt: %s", self.name, target, err
                )
                errors.append(f"{target}: {err}")

        if raise_on_error and errors:
            raise HomeAssistantError("Melding mislukt voor " + "; ".join(errors))


def _hours(hours: float) -> str:
    """'1 uur', '2 uur', '1,5 uur'."""
    value = float(hours)
    text = str(int(value)) if value.is_integer() else f"{value:g}".replace(".", ",")
    return f"{text} uur"
