const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function scanner() {
    const events = {}, frames = [], timers = [];
    let detected, stopped = 0;
    const elements = {
        location_code: {value: 'A & B'},
        preview: {getContext: () => ({})},
        jan: {value: '', style: {}},
        'scan-loading': {hidden: true},
    };
    const context = {
        LaBook: {url: path => '/labook' + path}, console,
        document: {
            addEventListener: (name, fn) => { events[name] = fn; },
            getElementById: id => elements[id],
            createElement: () => ({setAttribute() {}, getContext: () => ({})}),
        },
        navigator: {mediaDevices: {getUserMedia: async () => ({getTracks: () => [{stop() { stopped++; }}]})}},
        window: {innerWidth: 360, innerHeight: 720, location: {}, addEventListener() {}},
        Quagga: {onDetected: fn => { detected = fn; }},
        setTimeout: fn => timers.push(fn),
        requestAnimationFrame: fn => frames.push(fn),
    };
    vm.runInNewContext(fs.readFileSync('static/scanner.js', 'utf8'), context);
    events.DOMContentLoaded();
    await Promise.resolve();
    return {context, elements, frames, timers, scan: code => detected({codeResult: {code}}), stopped: () => stopped};
}

(async () => {
    const s = await scanner();
    for (let i = 0; i < 4; i++) s.scan('1921234567890');
    assert.equal(s.elements['scan-loading'].hidden, true, 'price barcode must not start navigation');
    for (let i = 0; i < 3; i++) s.scan('9781234567897');
    assert.equal(s.elements['scan-loading'].hidden, true, 'wait for stable repeated detection');
    s.scan('9781234567897');
    assert.equal(s.elements['scan-loading'].hidden, false);
    assert.equal(s.stopped(), 1);
    assert.equal(s.context.window.location.href, undefined, 'paint success before navigation');
    s.scan('9781234567897');
    assert.equal(s.frames.length, 1, 'do not queue duplicate navigation');
    s.frames.shift()();
    assert.equal(s.context.window.location.href, undefined);
    s.frames.shift()();
    assert.equal(s.context.window.location.href, '/labook/books/manage?dummy=0&location_code_override=A%20%26%20B&isbn=9781234567897');
    s.timers.shift()(); // A pending capture must exit after success, without reading the camera.
    assert.equal(s.timers.length, 0);
    console.log('Scanner confirmation, rejected barcode, loading paint, duplicate prevention and shelf URL checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
