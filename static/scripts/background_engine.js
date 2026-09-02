document.addEventListener("DOMContentLoaded", function () {

    const background = document.getElementById("depth-background");

    if (!background) {return;}

    const imageCount =
        parseInt(
            background.dataset.imageCount
        );


    /* =====================================================
       SETTINGS
       ===================================================== */

    const IMAGE_COUNT =
        Number(background.dataset.imageCount) || 42;

    const IMAGE_FOLDER =
        background.dataset.imageFolder;


    /* =====================================================
       DEPTH SETTINGS

       Layer 1 = closest
       Layer 10 = farthest

       Closest image = 25vw

       Each layer is smaller than the previous one,
       but NOT by 50%.

       This gives us a visible depth effect instead
       of making the distant pictures microscopic.
       ===================================================== */

    const DEPTH_SCALES = {

         1: 1,
        2: 0.50,
        3: 0.25,
        4: 0.125,
        5: 0.0625,
        6: 0.03125,
        7: 0.015625,
        8: 0.0078125,
        9: 0.00390625,
        10: 0.001953125

    };


    /* =====================================================
       NUMBER OF IMAGES

       IMPORTANT:

       Closest layers = fewer images
       Distant layers = more images

       This creates the feeling that the viewer is
       surrounded by many distant objects while only
       a few large objects pass close to the viewer.
       ===================================================== */

    const OBJECTS_PER_LEVEL = {

        1: 10,
        2: 6,
        3: 10,
        4: 10,
        5: 10,
        6: 5,
        7: 4,
        8: 7,
        9: 8,
        10: 10

    };


    /* =====================================================
       DEPTH SPEED

       Closest = fastest
       Farthest = slowest
       ===================================================== */

    const DEPTH_SPEEDS = {

        1: 1.00,
        2: 0.92,
        3: 0.84,
        4: 0.76,
        5: 0.68,
        6: 0.60,
        7: 0.52,
        8: 0.45,
        9: 0.38,
        10: 0.32

    };


    /* =====================================================
       RANDOM FUNCTIONS
       ===================================================== */

    function randomInt(min, max) {

        return Math.floor(
            Math.random() * (max - min + 1)
        ) + min;

    }


    function random(min, max) {

        return Math.random() *
            (max - min) + min;

    }


    /* =====================================================
       RANDOM IMAGE
       ===================================================== */

    function randomImage() {

        const number =
            randomInt(1, IMAGE_COUNT);

        return `${IMAGE_FOLDER}/class_pics%20(${number}).jpg`;

    }


    /* =====================================================
       CREATE ONE PHOTO
       ===================================================== */

    function createObject(level) {

        const layer =
            background.querySelector(
                `.depth-${level}`
            );

        if (!layer) {
            return;
        }


        const object =
            document.createElement("div");

        object.className =
            "depth-object depth-frame";


        /* =================================================
           SIZE

           Layer 1 = 25vw

           Everything behind it becomes progressively
           smaller.
           ================================================= */

       const baseSize = window.innerWidth * 0.25;

        const size =
            baseSize * DEPTH_SCALES[level];

        object.style.setProperty(
            "--size",
            `${size}px`
        );


        object.style.setProperty(
            "--depth-scale",
            DEPTH_SCALES[level]
        );


        /* =================================================
           POSITION

           Keep the photographs spread around the screen.
           ================================================= */

        const startX =
            random(-20, 120);

        const startY =
            random(5, 95);


        object.style.setProperty(
            "--x",
            `${startX}vw`
        );

        object.style.setProperty(
            "--y",
            `${startY}vh`
        );


        /* =================================================
           ROTATION

           Farther images rotate less.
           ================================================= */

        const rotationAmount =
            6 * DEPTH_SCALES[level];

        const rotation =
            random(
                -rotationAmount,
                rotationAmount
            );


        object.style.setProperty(
            "--rotation",
            `${rotation}deg`
        );


        /* =================================================
           SPEED

           The farther away the object is,
           the slower it moves.
           ================================================= */

        const speed =
            DEPTH_SPEEDS[level];


        const baseDuration =
            random(45, 65);


        const duration =
            baseDuration / speed;


        object.style.setProperty(
            "--duration",
            `${duration}s`
        );


        /* =================================================
           RANDOM START

           Negative delay means the animation begins
           somewhere in the middle rather than making
           every photograph appear simultaneously.
           ================================================= */

        const delay =
            random(-duration, 0);


        object.style.setProperty(
            "--delay",
            `${delay}s`
        );


        /* =================================================
           DIRECTION
           ================================================= */

        const direction =
            Math.random() < 0.5
                ? "depth-moving-left"
                : "depth-moving-right";


        object.classList.add(direction);


        /* =================================================
           IMAGE
           ================================================= */

        const image =
            document.createElement("img");


        image.src =
            randomImage();


        image.alt = "";


        image.onerror =
            function () {

                object.remove();

            };


        object.appendChild(image);


        layer.appendChild(object);

    }


   /* =====================================================
       BUILD BACKGROUND

       Farthest layers first.
       Closest layers last.

       This makes the depth order explicit.
       ===================================================== */

    for (let level = 10; level >= 1; level--) {

        const count =
            OBJECTS_PER_LEVEL[level];


        for (let i = 0; i < count; i++) {

            createObject(level);

        }

    }

});