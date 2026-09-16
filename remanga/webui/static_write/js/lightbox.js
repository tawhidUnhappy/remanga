// A panel's image at full size, over the page. Click anywhere (or Escape) to
// close - there is nothing to interact with inside it.

export function openLightbox(src, alt) {
  const img = document.getElementById("lightbox-img");
  img.src = src;
  img.alt = alt;
  document.getElementById("lightbox").classList.add("open");
}

function closeLightbox() {
  document.getElementById("lightbox").classList.remove("open");
}

export function wireLightbox() {
  document.getElementById("lightbox").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });
}
