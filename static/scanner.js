// scanner.js
const BASE_URL = "{{ manage_book_url }}";
var DetectedCount = 0, DetectedCode = "";
var video, tmp, tmp_ctx, jan, prev, prev_ctx, w, h, mw, mh, x1, y1;
var base_url = "/books/manage?dummy=0";
var stream;
document.addEventListener('DOMContentLoaded', function () {
    location_code = document.getElementById("location_code").value;
    if (location_code != "None") base_url += "&location_code_override=" + encodeURIComponent(location_code);
    video = document.createElement('video');
    video.setAttribute("autoplay", "");
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    video.onloadedmetadata = function (e) { video.play(); };
    prev = document.getElementById("preview");
    prev_ctx = prev.getContext("2d", { willReadFrequently: true });
    tmp = document.createElement('canvas');
    tmp_ctx = tmp.getContext("2d", { willReadFrequently: true });
    jan = document.getElementById("jan");


    navigator.mediaDevices.getUserMedia(
        { "audio": false, "video": { "facingMode": "environment", "width": { "ideal": Math.min(window.innerWidth - 100, 900) }, "height": { "ideal": Math.min(window.innerHeight - 300, 900) } } }
    ).then(
        function (s) {
            stream = s;
            video.srcObject = stream;
            setTimeout(Scan, 500, true);
        }
    ).catch(
        function (err) {
            alert(err);
            console.error(err);
        }
    );

    function Scan(first) {
        if (first) {
            w = video.videoWidth;
            h = video.videoHeight;
            prev.style.width = w;
            prev.style.height = h;
            prev.setAttribute("width", w);
            prev.setAttribute("height", h);
            mw = w * 0.5;
            mh = w * 0.2;
            x1 = (w - mw) / 2;
            y1 = (h - mh) / 2;
        }
        prev_ctx.drawImage(video, 0, 0, w, h);
        prev_ctx.beginPath();
        prev_ctx.strokeStyle = "rgb(255,0,0)";
        prev_ctx.lineWidth = 2;
        if (DetectedCount < 0) {
            prev_ctx.strokeStyle = "rgb(0,255,0)";
            prev_ctx.lineWidth = 5;
        }
        prev_ctx.rect(x1, y1, mw, mh);
        prev_ctx.stroke();
        tmp.setAttribute("width", mw);
        tmp.setAttribute("height", mh);
        tmp_ctx.drawImage(prev, x1, y1, mw, mh, 0, 0, mw, mh);

        tmp.toBlob(function (blob) {
            let reader = new FileReader();
            reader.onload = function () {
                let config = {
                    decoder: {
                        readers: ["ean_reader"],
                        multiple: false,
                    },
                    locator: { patchSize: "large", halfSample: false },
                    locate: false,
                    src: reader.result,
                };
                Quagga.decodeSingle(config, function () { });
            }
            reader.readAsDataURL(blob);
        });
        setTimeout(Scan, 50, false);
    }

    Quagga.onDetected(function (result) {
        if (DetectedCount < 0) {
            DetectedCount = -1;
            return;
        }
        if (DetectedCode == result.codeResult.code) {
            DetectedCount++;
        } else {
            DetectedCount = 0;
            DetectedCode = result.codeResult.code;
        }
        if (DetectedCount >= 3) {
            console.log(result.codeResult.code);
            jan.value = result.codeResult.code;
            if (result.codeResult.code.startsWith("192")) {
                jan.style.color = "red";
                DetectedCode = '';
                DetectedCount = 0;
            } else {
                if (result.codeResult.code.startsWith("978") || result.codeResult.code.startsWith("979") || result.codeResult.code.startsWith("978-4")) {
                    jan.style.color = "green";
                } else {
                    jan.style.color = "black";
                }
                window.location.href = base_url + "&isbn=" + encodeURIComponent(result.codeResult.code);
                DetectedCount = -1;
            }
        }
    });

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
                stream = null;
                video.srcObject = null;
            }
        } else {
            navigator.mediaDevices.getUserMedia(
                { "audio": false, "video": { "facingMode": "environment", "width": { "ideal": Math.min(window.innerWidth - 100, 900) }, "height": { "ideal": Math.min(window.innerHeight - 300, 900) } } }
            ).then(
                function (s) {
                    stream = s;
                    video.srcObject = stream;
                }
            ).catch(
                function (err) {
                    alert(err);
                    console.error(err);
                }
            );
        }
    });
});
