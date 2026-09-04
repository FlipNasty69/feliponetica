document.addEventListener("DOMContentLoaded", function () {

    const background = document.getElementById("depth-background");

    if (!background) {
        return;
    }

    const imageCount = Number(background.dataset.imageCount) || 0;
    const imageFolder = (background.dataset.imageFolder || "").replace(/\/$/, "");
    const imagePrefix = background.dataset.imagePrefix || "class_pics";
    const extensions = (background.dataset.imageExtensions || "jpg,jpeg,png,webp")
        .split(",")
        .map(function (extension) {
            return extension.trim().replace(/^\./, "");
        })
        .filter(Boolean);

    if (!imageCount || !imageFolder) {
        return;
    }

    const depthScales = [1, 0.72, 0.52, 0.38, 0.28, 0.20, 0.14, 0.10, 0.07, 0.05];
    const depthOpacity = [1, 0.84, 0.66, 0.51, 0.39, 0.29, 0.21, 0.15, 0.10, 0.06];
    const depthDuration = [75, 88, 102, 118, 136, 155, 176, 198, 222, 248];

    function random(min, max) {
        return Math.random() * (max - min) + min;
    }

    function randomInt(min, max) {
        return Math.floor(random(min, max + 1));
    }

    function setProperty(element, name, value) {
        element.style.setProperty(name, value);
    }

    function ensureLayers() {
        for (let level = 10; level >= 1; level -= 1) {
            let layer = background.querySelector(".depth-" + level);

            if (!layer) {
                layer = document.createElement("div");
                layer.className = "depth-layer depth-" + level;
                background.appendChild(layer);
            }
        }
    }

    function getTrajectory() {
        const side = randomInt(0, 3);
        let startX;
        let startY;
        let endX;
        let endY;

        if (side === 0) {
            startX = random(-25, 125);
            startY = random(-35, -15);
            endX = startX + random(-55, 55);
            endY = random(115, 140);
        } else if (side === 1) {
            startX = random(0, 100);
            startY = random(115, 140);
            endX = startX + random(-55, 55);
            endY = random(-35, -15);
        } else if (side === 2) {
            startX = random(-35, -15);
            startY = random(-20, 120);
            endX = random(115, 140);
            endY = startY + random(-45, 45);
        } else {
            startX = random(115, 140);
            startY = random(-20, 120);
            endX = random(-35, -15);
            endY = startY + random(-45, 45);
        }

        return {
            startX: startX,
            startY: startY,
            endX: endX,
            endY: endY
        };
    }

    function createObject(imageNumber, level) {
        const layer = background.querySelector(".depth-" + level);
        const object = document.createElement("div");
        const image = document.createElement("img");
        const trajectory = getTrajectory();
        const scale = depthScales[level - 1];
        const duration = random(depthDuration[level - 1] * 0.82, depthDuration[level - 1] * 1.18);
        let extensionIndex = 0;

        object.className = "depth-object depth-frame";
        image.alt = "";
        image.decoding = "async";

        setProperty(object, "--size", window.innerWidth * 0.25 + "px");
        setProperty(object, "--depth-scale", scale);
        setProperty(object, "--depth-opacity", depthOpacity[level - 1]);
        setProperty(object, "--start-x", trajectory.startX + "vw");
        setProperty(object, "--start-y", trajectory.startY + "vh");
        setProperty(object, "--end-x", trajectory.endX + "vw");
        setProperty(object, "--end-y", trajectory.endY + "vh");
        setProperty(object, "--start-rotation", random(-14, 14) + "deg");
        setProperty(object, "--end-rotation", random(-14, 14) + "deg");
        setProperty(object, "--duration", duration + "s");
        setProperty(object, "--delay", random(-duration, 0) + "s");

        function loadImage() {
            if (extensionIndex >= extensions.length) {
                object.remove();
                return;
            }

            image.src = imageFolder + "/" + imagePrefix + "%20(" + imageNumber + ")." + extensions[extensionIndex];
            extensionIndex += 1;
        }

        image.onerror = loadImage;
        loadImage();
        object.appendChild(image);
        layer.appendChild(object);
    }

    ensureLayers();

    for (let imageNumber = 1; imageNumber <= imageCount; imageNumber += 1) {
        const level = ((imageNumber - 1) % 10) + 1;
        createObject(imageNumber, level);
    }
});
