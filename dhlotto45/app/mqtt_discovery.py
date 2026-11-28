"""
MQTT Discovery Helper for Home Assistant
Provides unique_id support for sensors
"""

import json
import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

TOPIC_PREFIX = "dhlotto"


class MQTTDiscovery:
    """MQTT Discovery helper class"""

    def __init__(self, mqtt_url: str, username: Optional[str] = None, password: Optional[str] = None, client_id_suffix: str = ""):
        """Initialize MQTT Discovery

        Args:
            mqtt_url: MQTT URL (e.g., "mqtt://core-mosquitto:1883" or "homeassistant.local:1883")
            username: MQTT username (optional)
            password: MQTT password (optional)
            client_id_suffix: Client ID suffix for beta version (optional)
        """
        # Parse MQTT URL
        self.broker, self.port = self._parse_mqtt_url(mqtt_url)
        self.username_mqtt = username
        self.password_mqtt = password
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.connecting = False
        # 재연결 때 다시 구독할 토픽, 연결(재연결)될 때마다 부를 콜백(paho 스레드에서 호출됨)
        self.subscriptions: set = set()
        self.on_ready = None
        self.last_error = ""
        self._last_logged_rc = None
        self.topic_prefix = TOPIC_PREFIX + client_id_suffix if client_id_suffix else TOPIC_PREFIX

    @staticmethod
    def _parse_mqtt_url(mqtt_url: str) -> tuple:
        """Parse MQTT URL

        Args:
            mqtt_url: MQTT URL (e.g., "mqtt://core-mosquitto:1883" or "homeassistant.local:1883")

        Returns:
            tuple: (broker, port)
        """
        # Add mqtt:// prefix if not present
        if not mqtt_url.startswith("mqtt://"):
            mqtt_url = f"mqtt://{mqtt_url}"

        parsed = urlparse(mqtt_url)
        broker = parsed.hostname or "homeassistant.local"
        port = parsed.port or 1883

        return broker, port

    # CONNACK 코드 → 사용자가 고칠 수 있는 설명
    RC_REASONS = {
        1: "브로커가 MQTT 프로토콜 버전을 거부함",
        2: "브로커가 클라이언트 ID 를 거부함",
        3: "브로커를 사용할 수 없음(브로커가 아직 시작 중일 수 있음)",
        4: "MQTT 아이디 또는 비밀번호가 틀림",
        5: "MQTT 인증 거부(계정이 없거나 권한 없음)",
    }

    def connect(self, wait: float = 10.0) -> bool:
        """브로커에 연결한다. 연결이 안 돼도 백그라운드에서 계속 재시도한다(HA 재부팅 시 브로커가 늦게 뜨는 경우).

        wait 초 동안 연결을 기다린 뒤 현재 연결 여부를 돌려준다. 연결(재연결)될 때마다 on_ready 가 불린다.
        """
        if self.client is None:
            self.client = mqtt.Client(client_id="dhlottery_addon", protocol=mqtt.MQTTv311)
            if self.username_mqtt:
                self.client.username_pw_set(self.username_mqtt, self.password_mqtt or None)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.reconnect_delay_set(min_delay=2, max_delay=60)
            _LOGGER.info(
                f"Connecting to MQTT broker: {self.broker}:{self.port} "
                f"(인증: {'아이디 사용' if self.username_mqtt else '없음'})"
            )
            try:
                self.client.connect_async(self.broker, self.port, 60)
                self.client.loop_start()
            except Exception as e:  # noqa: BLE001
                self.last_error = f"브로커 주소를 사용할 수 없음: {e}"
                _LOGGER.error(f"[MQTT] {self.last_error}")
                return False
        deadline = time.time() + wait
        while not self.connected and time.time() < deadline:
            time.sleep(0.1)
        if not self.connected:
            reason = self.last_error or "응답 없음(브로커 주소·포트를 확인하세요)"
            _LOGGER.error(f"[MQTT] 아직 연결되지 않음: {reason}. 백그라운드에서 계속 재시도합니다.")
        return self.connected

    def subscribe(self, topic: str) -> None:
        """구독하고 기억해 둔다(재연결 시 자동으로 다시 구독)."""
        self.subscriptions.add(topic)
        if self.client is not None and self.connected:
            self.client.subscribe(topic)

    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False

    def _on_connect(self, client, userdata, flags, rc):
        """연결(재연결) 결과. 성공하면 구독을 복구하고 on_ready 를 부른다."""
        rc = int(getattr(rc, "value", rc))
        if rc == 0:
            self.connected = True
            self.last_error = ""
            self._last_logged_rc = None
            _LOGGER.info("Connected to MQTT broker")
            for topic in sorted(self.subscriptions):
                client.subscribe(topic)
            if self.on_ready:
                try:
                    self.on_ready()
                except Exception as e:  # noqa: BLE001
                    _LOGGER.error(f"[MQTT] 연결 후 처리 실패: {e}")
        else:
            self.connected = False
            self.last_error = self.RC_REASONS.get(rc, f"연결 거부(코드 {rc})")
            if rc != self._last_logged_rc:  # 같은 오류를 재시도마다 반복 기록하지 않음
                self._last_logged_rc = rc
                hint = ""
                if rc in (4, 5):
                    hint = (" → 애드온 구성의 mqtt_username·mqtt_password 를 비우면 Mosquitto broker 가 "
                            "이 애드온 전용 계정을 자동으로 줍니다. 직접 넣었다면 그 계정이 브로커에 있는지 확인하세요.")
                _LOGGER.error(f"[MQTT] 연결 실패: {self.last_error}{hint}")

    def _on_disconnect(self, client, userdata, rc):
        """연결이 끊기면 paho 가 자동으로 재연결한다."""
        self.connected = False
        rc = int(getattr(rc, "value", rc))
        if rc != 0:
            _LOGGER.warning(f"[MQTT] 브로커 연결 끊김(코드 {rc}) — 자동으로 다시 연결합니다")

    def publish_sensor_discovery(
        self,
        sensor_id: str,
        name: str,
        state_topic: str,
        username: str,
        device_name: Optional[str] = None,
        device_identifier: Optional[str] = None,
        unit_of_measurement: Optional[str] = None,
        device_class: Optional[str] = None,
        icon: Optional[str] = None,
        value_template: Optional[str] = None,
        json_attributes_topic: Optional[str] = None,
    ) -> bool:
        """
        Publish sensor discovery configuration

        Args:
            sensor_id: Sensor ID (e.g., 'balance', 'hot_numbers')
            name: Friendly name
            state_topic: MQTT topic for state
            username: DH Lottery username (for unique_id)
            device_name: Device name (optional, uses default if not provided)
            device_identifier: Device identifier (optional, uses default if not provided)
            unit_of_measurement: Unit (e.g., 'KRW', 'times')
            device_class: Device class (e.g., 'timestamp', 'date')
            icon: Icon (e.g., 'mdi:wallet')
            value_template: Jinja2 template for value
            json_attributes_topic: Topic for attributes
        """
        if not self.connected:
            _LOGGER.warning("Not connected to MQTT broker")
            return False

        # Use default device if not specified
        if not device_name:
            device_name = f"DH Lottery Addon ({username})"
        if not device_identifier:
            device_identifier = f"{TOPIC_PREFIX}_addon_{username}"

        # Discovery topic: homeassistant/sensor/dhlotto_USERNAME_SENSOR_ID/config
        discovery_topic = f"homeassistant/sensor/{TOPIC_PREFIX}_{username}_{sensor_id}/config"

        # Unique ID: dhlotto_USERNAME_SENSOR_ID
        unique_id = f"{TOPIC_PREFIX}_{username}_{sensor_id}"

        # Entity ID: sensor.dhlotto_USERNAME_SENSOR_ID
        object_id = f"{TOPIC_PREFIX}_{username}_{sensor_id}"

        config = {
            "name": name,
            "unique_id": unique_id,
            "object_id": object_id,
            "state_topic": state_topic,
            "has_entity_name": False,  # Prevent device name prefix
            "device": {
                "identifiers": [device_identifier],
                "name": device_name,
                "manufacturer": "dhlottery.co.kr",
                "model": "토스 1000-1261-7813 우*만",
                "sw_version": "커피 한잔은 사랑입니다",
            },
        }

        # Optional fields
        if unit_of_measurement:
            config["unit_of_measurement"] = unit_of_measurement
        if device_class:
            config["device_class"] = device_class
        if icon:
            config["icon"] = icon
        if value_template:
            config["value_template"] = value_template
        if json_attributes_topic:
            config["json_attributes_topic"] = json_attributes_topic

        try:
            payload = json.dumps(config)
            result = self.client.publish(discovery_topic, payload, qos=1, retain=True)
            result.wait_for_publish()
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to publish discovery for {sensor_id}: {e}")
            return False

    def publish_sensor_state(self, sensor_id: str, username: str, state: Any,
                            attributes: Optional[Dict[str, Any]] = None) -> bool:
        """
        Publish sensor state

        Args:
            sensor_id: Sensor ID
            username: DH Lottery username
            state: Sensor state value
            attributes: Optional attributes dictionary
        """
        if not self.connected:
            _LOGGER.warning("Not connected to MQTT broker")
            return False

        # State topic
        state_topic = f"homeassistant/sensor/{TOPIC_PREFIX}_{username}_{sensor_id}/state"

        try:
            # Publish state
            result = self.client.publish(state_topic, str(state), qos=1, retain=True)
            result.wait_for_publish()

            # Publish attributes if provided
            if attributes:
                attr_topic = f"homeassistant/sensor/{TOPIC_PREFIX}_{username}_{sensor_id}/attributes"
                attr_payload = json.dumps(attributes)
                result = self.client.publish(attr_topic, attr_payload, qos=1, retain=True)
                result.wait_for_publish()

            return True
        except Exception as e:
            _LOGGER.error(f"Failed to publish state for {sensor_id}: {e}")
            return False

    def remove_sensor(self, sensor_id: str, username: str) -> bool:
        """
        Remove sensor from Home Assistant (publish empty config)

        Args:
            sensor_id: Sensor ID
            username: DH Lottery username
        """
        if not self.connected:
            return False

        discovery_topic = f"homeassistant/sensor/{TOPIC_PREFIX}_{username}_{sensor_id}/config"

        try:
            result = self.client.publish(discovery_topic, "", qos=1, retain=True)
            result.wait_for_publish()
            _LOGGER.info(f"Removed sensor: {sensor_id}")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to remove sensor {sensor_id}: {e}")
            return False

    def publish_button_discovery(
        self,
        button_id: str,
        name: str,
        command_topic: str,
        username: str,
        device_name: str,
        device_identifier: str,
        icon: Optional[str] = None,
        device_class: Optional[str] = None,
    ) -> bool:
        """
        Publish button discovery configuration

        Args:
            button_id: Button ID (e.g., 'buy_auto_1', 'buy_auto_5')
            name: Friendly name
            command_topic: MQTT topic for commands
            username: DH Lottery username
            device_name: Device name (e.g., "DH Lottery Lotto 645 (lotteuserid)")
            device_identifier: Device identifier (e.g., "dhlotto_lotteuserid_lotto645")
            icon: Icon (e.g., 'mdi:ticket-confirmation')
            device_class: Device class (e.g., 'restart')
        """
        if not self.connected:
            _LOGGER.warning("Not connected to MQTT broker")
            return False

        # Discovery topic: homeassistant/button/dhlotto_USERNAME_BUTTON_ID/config
        discovery_topic = f"homeassistant/button/{TOPIC_PREFIX}_{username}_{button_id}/config"

        # Unique ID: dhlotto_USERNAME_BUTTON_ID
        unique_id = f"{TOPIC_PREFIX}_{username}_{button_id}"

        # Entity ID: button.dhlotto_USERNAME_BUTTON_ID
        object_id = f"{TOPIC_PREFIX}_{username}_{button_id}"

        config = {
            "name": name,
            "unique_id": unique_id,
            "object_id": object_id,
            "command_topic": command_topic,
            "has_entity_name": False,  # Prevent device name prefix
            "device": {
                "identifiers": [device_identifier],
                "name": device_name,
                "manufacturer": "dhlottery.co.kr",
                "model": "토스 1000-1261-7813 우*만",
                "sw_version": "커피 한잔은 사랑입니다",
            },
        }

        # Optional fields
        if icon:
            config["icon"] = icon
        if device_class:
            config["device_class"] = device_class

        try:
            payload = json.dumps(config)
            _LOGGER.debug(f"Publishing button discovery: {discovery_topic}")
            _LOGGER.debug(f"Config: {payload}")
            result = self.client.publish(discovery_topic, payload, qos=1, retain=True)
            result.wait_for_publish()
            _LOGGER.info(f"Published button discovery: button.{object_id}")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to publish button discovery for {button_id}: {e}")
            return False

    def subscribe_to_commands(self, username: str, callback) -> bool:
        """
        Subscribe to button command topics and input text commands

        Args:
            username: DH Lottery username
            callback: Callback function to handle messages
        """
        if not self.connected:
            _LOGGER.warning("Not connected to MQTT broker")
            return False

        # Subscribe to all buttons and input text
        button_ids = ["buy_auto_1", "buy_auto_5", "buy_manual"]

        try:
            self.client.on_message = callback

            # Subscribe to button commands
            for button_id in button_ids:
                command_topic = f"homeassistant/button/{TOPIC_PREFIX}_{username}_{button_id}/command"
                result = self.client.subscribe(command_topic)
                _LOGGER.info(f"Subscribed to: {command_topic}")

            # Subscribe to input_text set command
            input_command_topic = f"homeassistant/text/{TOPIC_PREFIX}_{username}_manual_numbers/set"
            result = self.client.subscribe(input_command_topic)
            _LOGGER.info(f"Subscribed to: {input_command_topic}")

            _LOGGER.info("Waiting for button press and input text events...")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to subscribe to commands: {e}")
            return False

    def publish_input_text_discovery(
        self,
        input_id: str,
        name: str,
        state_topic: str,
        command_topic: str,
        username: str,
        device_name: str,
        device_identifier: str,
        icon: Optional[str] = None,
        mode: str = "text",
        min_length: int = 0,
        max_length: int = 255,
        pattern: Optional[str] = None,
    ) -> bool:
        """
        Publish input_text (text entity) discovery configuration

        Args:
            input_id: Input ID (e.g., 'manual_numbers')
            name: Friendly name
            state_topic: MQTT topic for state
            command_topic: MQTT topic for commands (set value)
            username: DH Lottery username
            device_name: Device name
            device_identifier: Device identifier
            icon: Icon (e.g., 'mdi:numeric')
            mode: Mode ('text' or 'password')
            min_length: Minimum length (default: 0)
            max_length: Maximum length (default: 255)
            pattern: Regex pattern for validation
        """
        if not self.connected:
            _LOGGER.warning("Not connected to MQTT broker")
            return False

        # Discovery topic: homeassistant/text/dhlotto_USERNAME_INPUT_ID/config
        discovery_topic = f"homeassistant/text/{TOPIC_PREFIX}_{username}_{input_id}/config"

        # Unique ID: dhlotto_USERNAME_INPUT_ID
        unique_id = f"{TOPIC_PREFIX}_{username}_{input_id}"

        # Entity ID: text.dhlotto_USERNAME_INPUT_ID
        object_id = f"{TOPIC_PREFIX}_{username}_{input_id}"

        config = {
            "name": name,
            "unique_id": unique_id,
            "object_id": object_id,
            "state_topic": state_topic,
            "command_topic": command_topic,
            "mode": mode,
            "min": min_length,
            "max": max_length,
            "has_entity_name": False,  # Prevent device name prefix
            "device": {
                "identifiers": [device_identifier],
                "name": device_name,
                "manufacturer": "dhlottery.co.kr",
                "model": "토스 1000-1261-7813 우*만",
                "sw_version": "커피 한잔은 사랑입니다",
            },
        }

        # Optional fields
        if icon:
            config["icon"] = icon
        if pattern:
            config["pattern"] = pattern

        try:
            payload = json.dumps(config)
            _LOGGER.debug(f"Publishing input_text discovery: {discovery_topic}")
            _LOGGER.debug(f"Config: {payload}")
            result = self.client.publish(discovery_topic, payload, qos=1, retain=True)
            result.wait_for_publish()
            _LOGGER.info(f"Published input_text discovery: text.{object_id}")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to publish input_text discovery for {input_id}: {e}")
            return False


async def publish_sensor_mqtt(
    mqtt_client: MQTTDiscovery,
    entity_id: str,
    state: Any,
    username: str,
    attributes: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Helper function to publish sensor via MQTT Discovery

    Args:
        mqtt_client: MQTT Discovery client
        entity_id: Entity ID (e.g., 'lotto45_balance')
        state: Sensor state
        username: DH Lottery username
        attributes: Sensor attributes (includes friendly_name, icon, etc.)
    """
    if not mqtt_client or not mqtt_client.connected:
        return False

    # Extract metadata from attributes
    friendly_name = attributes.get("friendly_name", entity_id) if attributes else entity_id
    unit = attributes.get("unit_of_measurement")
    device_class = attributes.get("device_class")
    icon = attributes.get("icon")

    # Prepare state topic
    state_topic = f"homeassistant/sensor/{TOPIC_PREFIX}_{username}_{entity_id}/state"

    # Prepare attributes topic
    json_attributes_topic = None
    if attributes:
        json_attributes_topic = f"homeassistant/sensor/{TOPIC_PREFIX}_{username}_{entity_id}/attributes"

    # Only log important sensors
    is_important = "purchase" in entity_id or "latest" in entity_id
    if is_important:
        _LOGGER.info(f"Publishing MQTT sensor: {entity_id} = {state}")

    # Publish discovery config (only once, but retained)
    mqtt_client.publish_sensor_discovery(
        sensor_id=entity_id,
        name=friendly_name,
        state_topic=state_topic,
        username=username,
        unit_of_measurement=unit,
        device_class=device_class,
        icon=icon,
        json_attributes_topic=json_attributes_topic,
    )

    # Publish state
    result = mqtt_client.publish_sensor_state(
        sensor_id=entity_id,
        username=username,
        state=state,
        attributes=attributes
    )

    if is_important and result:
        _LOGGER.info(f"MQTT sensor published: {entity_id}")

    return result

