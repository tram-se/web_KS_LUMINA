document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector("input[name=gallery_images]");
  if (!input) return;
  input.addEventListener("change", () => {
    let preview = document.getElementById("gallery-upload-preview");
    if (!preview) {
      preview = document.createElement("div");
      preview.id = "gallery-upload-preview";
      input.parentElement.appendChild(preview);
    }
    preview.innerHTML = "";
    const files = Array.from(input.files);
    files.forEach((file, index) => {
      if (!file.type.startsWith("image/")) return;
      const item = document.createElement("span");
      item.style.cssText =
        "display:inline-flex;flex-direction:column;margin:8px 8px 0 0;vertical-align:top";
      const image = document.createElement("img");
      image.src = URL.createObjectURL(file);
      image.alt = file.name;
      image.style.cssText = "width:110px;height:80px;object-fit:cover";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Xóa";
      remove.addEventListener("click", () => {
        const transfer = new DataTransfer();
        files.forEach((current, currentIndex) => {
          if (currentIndex !== index) transfer.items.add(current);
        });
        input.files = transfer.files;
        input.dispatchEvent(new Event("change"));
      });
      item.append(image, remove);
      preview.appendChild(item);
    });
  });
});
