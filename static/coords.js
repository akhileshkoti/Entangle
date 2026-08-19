// Maps a client (viewport) coordinate to device pixel space, accounting
// for the letterboxing that `object-fit: contain` introduces when the
// video element's aspect ratio doesn't match the device's.
function normalizeCoords(clientX, clientY, videoEl, deviceW, deviceH) {
  const rect = videoEl.getBoundingClientRect();
  const elAspect = rect.width / rect.height;
  const devAspect = deviceW / deviceH;

  let dispW, dispH, offsetX, offsetY;
  if (elAspect > devAspect) {
    dispH = rect.height;
    dispW = dispH * devAspect;
    offsetX = (rect.width - dispW) / 2;
    offsetY = 0;
  } else {
    dispW = rect.width;
    dispH = dispW / devAspect;
    offsetX = 0;
    offsetY = (rect.height - dispH) / 2;
  }

  const relX = clientX - rect.left - offsetX;
  const relY = clientY - rect.top - offsetY;

  const x = Math.max(0, Math.min(deviceW - 1, Math.round((relX / dispW) * deviceW)));
  const y = Math.max(0, Math.min(deviceH - 1, Math.round((relY / dispH) * deviceH)));
  return { x, y };
}
