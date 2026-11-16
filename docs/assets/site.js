// FreeFox website: Mermaid diagrams and copy buttons. Shared by the EN and FR pages.
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";

mermaid.initialize({
  startOnLoad: true,
  theme: "base",
  themeVariables: {
    fontFamily: '"Ubuntu Sans", system-ui, sans-serif',
    fontSize: "15px",
    background: "#21140A",
    primaryColor: "#FFF3E8",
    primaryTextColor: "#1A0A00",
    primaryBorderColor: "#FF9A4D",
    lineColor: "#FF8A33",
    textColor: "#EFE6DA",
    edgeLabelBackground: "#2A190D",
    clusterBkg: "#2A190D",
    clusterBorder: "#5A3A1F",
    titleColor: "#EFE6DA",
  },
  flowchart: { curve: "basis", htmlLabels: true },
});

for (const button of document.querySelectorAll("[data-copy]")) {
  button.addEventListener("click", async () => {
    const text = document.querySelector(button.dataset.copy)?.textContent ?? "";
    const label = button.textContent;
    try {
      await navigator.clipboard.writeText(text.trim());
      button.textContent = button.dataset.done || "Copied";
    } catch {
      button.textContent = "⚠";
    }
    setTimeout(() => (button.textContent = label), 1600);
  });
}
