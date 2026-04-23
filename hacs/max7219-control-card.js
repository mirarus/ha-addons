class Max7219ControlCard extends HTMLElement {
  static getStubConfig() {
    return {
      title: "MAX7219 Control",
      namespace: "mirarus/max7219",
    };
  }

  setConfig(config) {
    this._config = {
      title: config.title || "MAX7219 Control",
      namespace: (config.namespace || "mirarus/max7219").replace(/\/+$/, ""),
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateState();
  }

  connectedCallback() {
    this._render();
  }

  getCardSize() {
    return 4;
  }

  _topic(path) {
    return `${this._config.namespace}/${path}`;
  }

  _publish(topic, payload) {
    if (!this._hass) return;
    return this._hass.callService("mqtt", "publish", { topic, payload: String(payload) });
  }

  _sendCommand(command, value) {
    return this._publish(this._topic(`cmnd/${command}`), value);
  }

  async _sendSchedule(payloadObj) {
    return this._publish(this._topic("cmnd/schedule"), JSON.stringify(payloadObj));
  }

  _render() {
    if (!this._config) return;
    if (!this.content) {
      this.innerHTML = `
        <ha-card>
          <div class="card-content">
            <h3 id="title"></h3>
            <div class="row">
              <ha-textfield id="text" label="Text"></ha-textfield>
              <mwc-button raised id="sendText">Send Text</mwc-button>
            </div>
            <div class="row">
              <ha-select id="mode">
                <mwc-list-item value="text">text</mwc-list-item>
                <mwc-list-item value="clock">clock</mwc-list-item>
              </ha-select>
              <mwc-button raised id="sendMode">Send Mode</mwc-button>
            </div>
            <div class="row">
              <ha-select id="effect">
                <mwc-list-item value="static">static</mwc-list-item>
                <mwc-list-item value="scroll">scroll</mwc-list-item>
                <mwc-list-item value="marquee">marquee</mwc-list-item>
                <mwc-list-item value="blink">blink</mwc-list-item>
                <mwc-list-item value="invert">invert</mwc-list-item>
                <mwc-list-item value="wave">wave</mwc-list-item>
              </ha-select>
              <mwc-button raised id="sendEffect">Send Effect</mwc-button>
            </div>
            <div class="row">
              <ha-textfield id="brightness" label="Brightness (0-255)" type="number"></ha-textfield>
              <mwc-button raised id="sendBrightness">Send Brightness</mwc-button>
            </div>
            <details>
              <summary>Quick Schedule</summary>
              <div class="row">
                <ha-textfield id="schTime" label="Time (HH:MM)" value="08:00"></ha-textfield>
                <ha-textfield id="schText" label="Text"></ha-textfield>
              </div>
              <mwc-button id="sendSchedule">Add Schedule</mwc-button>
            </details>
            <div id="state"></div>
          </div>
        </ha-card>
      `;

      const root = this;
      root.querySelector("#sendText").addEventListener("click", () => {
        root._sendCommand("text", root.querySelector("#text").value || "");
      });
      root.querySelector("#sendMode").addEventListener("click", () => {
        root._sendCommand("mode", root.querySelector("#mode").value || "text");
      });
      root.querySelector("#sendEffect").addEventListener("click", () => {
        root._sendCommand("effect", root.querySelector("#effect").value || "static");
      });
      root.querySelector("#sendBrightness").addEventListener("click", () => {
        root._sendCommand("brightness", root.querySelector("#brightness").value || "5");
      });
      root.querySelector("#sendSchedule").addEventListener("click", async () => {
        const payload = {
          time: root.querySelector("#schTime").value || "08:00",
          text: root.querySelector("#schText").value || "HELLO",
          mode: "text",
          effect: "scroll",
          duration: 60,
          enabled: true,
          days: [0, 1, 2, 3, 4, 5, 6],
        };
        await root._sendSchedule(payload);
      });
    }

    this.querySelector("#title").textContent = this._config.title;
    this._updateState();
  }

  _updateState() {
    if (!this._hass || !this._config || !this.content) return;
    const topic = this._topic("stat/state");
    const entity = Object.values(this._hass.states).find(
      (s) => s.attributes && s.attributes.topic === topic
    );

    const stateBox = this.querySelector("#state");
    if (!stateBox) return;

    if (!entity) {
      stateBox.innerHTML = `<small>State sensor not found for topic: ${topic}</small>`;
      return;
    }

    let parsed = {};
    try {
      parsed = JSON.parse(entity.state || "{}");
    } catch (err) {
      parsed = { raw: entity.state };
    }
    stateBox.innerHTML = `<small><b>Live State:</b> ${JSON.stringify(parsed)}</small>`;
  }
}

customElements.define("max7219-control-card", Max7219ControlCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "max7219-control-card",
  name: "MAX7219 MQTT Control Card",
  description: "Control MAX7219 add-on via MQTT topics",
});
