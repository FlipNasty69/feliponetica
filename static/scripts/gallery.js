document.addEventListener("DOMContentLoaded", () => {
    const cards = document.querySelectorAll(".gallery-card");
    const dialog = document.querySelector(".gallery-dialog");
    const dialogImage = document.querySelector(".gallery-dialog-image");
    const dialogCaption = document.querySelector(".gallery-dialog-caption");
    const closeButton = document.querySelector(".gallery-dialog-close");
    const loadMoreButton = document.querySelector("#gallery-load-more");
    const pageSize = 12;
    let visibleCount = pageSize;

    function loadThumbnail(image) {
        image.src = image.dataset.src;
        image.removeAttribute("data-src");
    }

    const imageObserver = "IntersectionObserver" in window
        ? new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    loadThumbnail(entry.target);
                    observer.unobserve(entry.target);
                }
            });
        }, { rootMargin: "250px" })
        : null;

    function updateGallery() {
        const visibleCards = new Set([...cards].slice(0, visibleCount));

        cards.forEach((card) => {
            card.hidden = !visibleCards.has(card);
        });
        [...cards].slice(0, visibleCount).forEach((card) => {
            const image = card.querySelector("img[data-src]");
            if (!image) return;
            if (imageObserver) {
                imageObserver.observe(image);
            } else {
                loadThumbnail(image);
            }
        });

        loadMoreButton.hidden = cards.length <= visibleCount;
    }

    loadMoreButton.addEventListener("click", () => {
        visibleCount += pageSize;
        updateGallery();
    });

    cards.forEach((card) => {
        card.addEventListener("click", () => {
            dialogImage.src = card.dataset.fullImage;
            dialogImage.alt = card.dataset.imageName;
            dialogCaption.textContent = card.dataset.imageName;
            dialog.showModal();
        });
    });

    closeButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) {
            dialog.close();
        }
    });
    dialog.addEventListener("close", () => {
        dialogImage.removeAttribute("src");
        dialogImage.alt = "";
        dialogCaption.textContent = "";
    });

    updateGallery();
});
