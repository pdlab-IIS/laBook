(function () {
    'use strict';

    const storageKey = 'labook-development-preview-mode-v2';
    const positionStorageKey = 'labook-development-preview-position-v1';
    const validModes = new Set(['sp700', 'pc', 'device']);
    const viewportPadding = 8;

    function getSavedMode() {
        try {
            const savedMode = window.localStorage.getItem(storageKey);
            return validModes.has(savedMode) ? savedMode : null;
        } catch (error) {
            return null;
        }
    }

    function saveMode(mode) {
        try {
            window.localStorage.setItem(storageKey, mode);
        } catch (error) {
            // The preview still works when storage is unavailable.
        }
    }

    function getSavedPosition() {
        try {
            const savedPosition = JSON.parse(
                window.localStorage.getItem(positionStorageKey)
            );
            if (
                Number.isFinite(savedPosition?.x) &&
                Number.isFinite(savedPosition?.y)
            ) {
                return {
                    x: Math.min(1, Math.max(0, savedPosition.x)),
                    y: Math.min(1, Math.max(0, savedPosition.y))
                };
            }
        } catch (error) {
            // Use the default CSS position when storage is unavailable.
        }
        return null;
    }

    function savePosition(position) {
        try {
            window.localStorage.setItem(
                positionStorageKey,
                JSON.stringify(position)
            );
        } catch (error) {
            // Dragging still works when storage is unavailable.
        }
    }

    function updateViewport(mode) {
        let viewport = document.querySelector('meta[name="viewport"]');
        if (!viewport) {
            viewport = document.createElement('meta');
            viewport.name = 'viewport';
            document.head.appendChild(viewport);
        }
        if (mode === 'sp700') {
            viewport.content = 'width=700';
        } else if (mode === 'pc') {
            viewport.content = 'width=1180';
        } else {
            viewport.content = 'width=device-width, initial-scale=1';
        }
    }

    function initializePreviewControls() {
        const overlay = document.getElementById('developmentEnvironmentOverlay');
        if (!overlay) return;

        const buttons = Array.from(
            overlay.querySelectorAll('[data-development-preview-mode]')
        );
        const description = document.getElementById('developmentPreviewDescription');
        let savedPosition = getSavedPosition();
        let dragState = null;

        function getPositionRange() {
            return {
                x: Math.max(
                    0,
                    window.innerWidth - overlay.offsetWidth - viewportPadding * 2
                ),
                y: Math.max(
                    0,
                    window.innerHeight - overlay.offsetHeight - viewportPadding * 2
                )
            };
        }

        function setOverlayPosition(left, top) {
            const range = getPositionRange();
            const clampedLeft = Math.min(
                viewportPadding + range.x,
                Math.max(viewportPadding, left)
            );
            const clampedTop = Math.min(
                viewportPadding + range.y,
                Math.max(viewportPadding, top)
            );

            overlay.style.left = `${clampedLeft}px`;
            overlay.style.top = `${clampedTop}px`;
            overlay.style.right = 'auto';
            overlay.style.bottom = 'auto';
        }

        function positionToRatio() {
            const rect = overlay.getBoundingClientRect();
            const range = getPositionRange();
            return {
                x: range.x === 0 ? 0 : (rect.left - viewportPadding) / range.x,
                y: range.y === 0 ? 0 : (rect.top - viewportPadding) / range.y
            };
        }

        function restoreSavedPosition() {
            if (!savedPosition) return;
            const range = getPositionRange();
            setOverlayPosition(
                viewportPadding + range.x * savedPosition.x,
                viewportPadding + range.y * savedPosition.y
            );
        }

        function moveDragging(clientX, clientY) {
            if (!dragState) return;
            setOverlayPosition(
                clientX - dragState.offsetX,
                clientY - dragState.offsetY
            );
        }

        function finishDragging(event) {
            if (
                !dragState ||
                (Number.isFinite(event.pointerId) &&
                    event.pointerId !== dragState.pointerId)
            ) {
                return;
            }
            const pointerId = dragState.pointerId;
            dragState = null;
            overlay.classList.remove('is-dragging');
            if (overlay.hasPointerCapture(pointerId)) {
                overlay.releasePointerCapture(pointerId);
            }
            savedPosition = positionToRatio();
            savePosition(savedPosition);
        }

        overlay.addEventListener('pointerdown', (event) => {
            if (
                event.button !== 0 ||
                event.target.closest('button, a, input, select, textarea')
            ) {
                return;
            }

            const rect = overlay.getBoundingClientRect();
            dragState = {
                pointerId: event.pointerId,
                offsetX: event.clientX - rect.left,
                offsetY: event.clientY - rect.top
            };
            overlay.setPointerCapture(event.pointerId);
            overlay.classList.add('is-dragging');
            event.preventDefault();
        });

        window.addEventListener('pointermove', (event) => {
            if (!dragState || event.pointerId !== dragState.pointerId) return;
            moveDragging(event.clientX, event.clientY);
        });

        window.addEventListener('pointerup', finishDragging);
        window.addEventListener('pointercancel', finishDragging);
        window.addEventListener('mousemove', (event) => {
            if (!dragState || event.buttons !== 1) return;
            moveDragging(event.clientX, event.clientY);
        });
        window.addEventListener('mouseup', finishDragging);
        window.addEventListener('resize', () => {
            window.requestAnimationFrame(restoreSavedPosition);
        });

        function applyMode(mode) {
            document.documentElement.dataset.developmentPreviewMode = mode;
            updateViewport(mode);
            buttons.forEach((button) => {
                button.setAttribute(
                    'aria-pressed',
                    String(button.dataset.developmentPreviewMode === mode)
                );
            });
            const descriptions = {
                sp700: 'SP preview: 700px fixed',
                pc: 'PC preview: 1180px fixed',
                device: 'Responsive: follows this device'
            };
            description.textContent = descriptions[mode];
            saveMode(mode);
            window.requestAnimationFrame(restoreSavedPosition);
        }

        buttons.forEach((button) => {
            button.addEventListener('click', () => {
                applyMode(button.dataset.developmentPreviewMode);
            });
        });

        applyMode(getSavedMode() || 'device');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializePreviewControls);
    } else {
        initializePreviewControls();
    }
})();
