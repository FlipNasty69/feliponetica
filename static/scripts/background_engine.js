document.addEventListener("DOMContentLoaded", function () {

    const background = document.getElementById("testimonial-bg") || document.getElementById("depth-background");

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

    const depthScales = [1, 0.9, 0.78, 0.68, 0.58, 0.48, 0.4, 0.34, 0.29, 0.24];
    const depthOpacity = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1];
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
            startX = random(-10, 110);
            startY = random(-15, -5);
            endX = startX + random(-35, 35);
            endY = random(105, 115);
        } else if (side === 1) {
            startX = random(0, 100);
            startY = random(105, 115);
            endX = startX + random(-35, 35);
            endY = random(-15, -5);
        } else if (side === 2) {
            startX = random(-15, -5);
            startY = random(-10, 110);
            endX = random(105, 115);
            endY = startY + random(-35, 35);
        } else {
            startX = random(105, 115);
            startY = random(-10, 110);
            endX = random(-15, -5);
            endY = startY + random(-35, 35);
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

        setProperty(object, "--size", Math.max(200, window.innerWidth * random(0.3, 0.6)) + "px");
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
