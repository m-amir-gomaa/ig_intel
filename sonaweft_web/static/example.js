"use strict";
async function loadExample() {
  const response = await fetch("/static/example/view.json");
  if (!response.ok)
    throw new Error(
      "The saved example could not load. Downloads remain available.",
    );
  const data = await response.json();
  const list = document.getElementById("example-segments");
  const audio = document.getElementById("example-audio");
  list.replaceChildren();
  for (const segment of data.segments) {
    const p = document.createElement("p");
    const button = document.createElement("button");
    button.className = "secondary";
    button.textContent =
      segment.start.toFixed(2) +
      "–" +
      segment.end.toFixed(2) +
      " s · " +
      segment.text;
    button.addEventListener("click", () => {
      audio.currentTime = segment.start;
      document.getElementById("example-status").textContent =
        "Recording moved to " +
        segment.start.toFixed(2) +
        " seconds. Press play to listen.";
    });
    p.append(button);
    list.append(p);
  }
  document.getElementById("example-summary").textContent = data.summary;
}
loadExample().catch((error) => {
  document.getElementById("example-status").textContent = error.message;
});
