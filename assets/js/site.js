function flash(button, text) {
  const label = button.textContent;
  button.textContent = text;
  button.classList.add("copied");
  setTimeout(() => {
    button.textContent = label;
    button.classList.remove("copied");
  }, 1500);
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-copy]");
  if (!button || button.classList.contains("copied")) return;
  try {
    await navigator.clipboard.writeText(button.dataset.copy);
    flash(button, "Copied");
  } catch {
    // Clipboard denied (permissions, embedded browser): select the hash for a manual copy.
    const range = document.createRange();
    range.selectNodeContents(button.previousElementSibling);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    flash(button, "Selected");
  }
});
