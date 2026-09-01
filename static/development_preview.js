(function () {
    'use strict';

    const storageKey = 'labook-development-preview-mode-v2';
    const validModes = new Set(['sp700', 'pc', 'device']);

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
