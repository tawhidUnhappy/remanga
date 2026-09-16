// A panel's image at full size, over the page. Click anywhere (or press
// Escape) to close - there is nothing to interact with inside it.
//
// Shared by the Narration Writer and the Narration Reviewer, which show the
// same panel images in the same list layout. Both pages carry the same
// #lightbox / #lightbox-img markup.

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
