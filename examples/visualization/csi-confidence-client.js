let csiConfidence = {
  left: 0,
  center: 0,
  right: 0,
  winner: "baseline",
  confidence: 0,
  clear: 1,
  active: false,
  ambiguous: false,
  topGap: 0,
  mirrored: false,
  rawChannels: { left: 0, center: 0, right: 0 },
  connected: false,
};

function connectCsiConfidence(url = "http://127.0.0.1:8765/events", onData = null) {
  const events = new EventSource(url);

  events.onmessage = (event) => {
    const data = JSON.parse(event.data);
    csiConfidence = {
      left: data.channels.left,
      center: data.channels.center,
      right: data.channels.right,
      winner: data.winner,
      confidence: data.confidence,
      clear: data.clear,
      active: data.active,
      ambiguous: data.ambiguous,
      topGap: data.top_gap,
      mirrored: data.mirrored,
      rawChannels: data.raw_channels,
      connected: true,
      raw: data,
    };

    if (onData) {
      onData(csiConfidence);
    }
  };

  events.onerror = () => {
    csiConfidence.connected = false;
  };

  return events;
}

// Example:
// connectCsiConfidence(undefined, (c) => {
//   console.log(c.left, c.center, c.right, c.winner);
// });
