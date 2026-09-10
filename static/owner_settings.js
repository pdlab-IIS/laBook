document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('ownerSettingsForm');
    if (!form) return;
    const entity = document.getElementById('ownerEntity');
    const name = document.getElementById('ownerEntityName');
    const kind = document.getElementById('ownerEntityType');
    const eligible = document.getElementById('ownerEntityEligible');
    const message = document.getElementById('ownerSettingsMessage');
    let busy = false;
    let enabledControls = [];

    function setBusy(value) {
        busy = value;
        if (value) {
            enabledControls = Array.from(document.querySelectorAll(
                '#ownerSettingsForm input, #ownerSettingsForm select, #ownerSettingsForm button, [data-edit-entity], [data-delete-entity]'
            )).filter(control => !control.disabled);
            enabledControls.forEach(control => { control.disabled = true; });
        } else {
            enabledControls.forEach(control => { control.disabled = false; });
        }
    }

    function refresh(result) {
        const url = new URL(window.location.href);
        url.searchParams.set('result', result);
        url.hash = 'people';
        window.location.assign(url.href);
    }

    function selectEntity() {
        const option = entity.selectedOptions[0];
        name.value = option?.dataset.name || '';
        kind.value = option?.dataset.type || 'person';
        eligible.value = option?.dataset.eligible || '0';
    }
    entity.addEventListener('change', selectEntity);
    document.querySelectorAll('[data-edit-entity]').forEach(control => {
        control.addEventListener('click', () => {
            if (busy) return;
            entity.value = control.dataset.editEntity;
            selectEntity();
            name.focus();
        });
    });
    document.querySelectorAll('[data-delete-entity]').forEach(control => {
        control.addEventListener('click', async () => {
            if (busy || control.disabled || !window.confirm(
                `「${control.dataset.name}」を削除しますか？この操作は元に戻せません。`
            )) return;
            setBusy(true);
            message.textContent = '削除中…';
            try {
                const response = await fetch(`/users/${control.dataset.deleteEntity}`, {method: 'DELETE'});
                if (response.ok) {
                    refresh('deleted');
                    return;
                }
                message.textContent = response.status === 409
                    ? '所有する本または貸出・返却履歴があるため削除できません。'
                    : '削除できませんでした。ページを開き直して状態を確認してください。';
            } catch (_) {
                message.textContent = '削除結果を確認できませんでした。再送前にページを開き直してください。';
            } finally {
                setBusy(false);
            }
        });
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (busy || !form.reportValidity()) return;
        const id = entity.value;
        const payload = {
            user_name: name.value.trim(),
            entity_type: kind.value,
            can_own_books: eligible.value === '1'
        };
        if (!payload.user_name) {
            message.textContent = '名前を入力してください。';
            return;
        }
        setBusy(true);
        message.textContent = '保存中…';
        try {
            const response = await fetch(id ? `/users/${id}` : '/users', {
                method: id ? 'PUT' : 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (!response.ok) {
                message.textContent = result.description || '保存できませんでした。';
                return;
            }
            refresh('saved');
        } catch (_) {
            message.textContent = '結果を確認できませんでした。再送前にページを開き直して候補設定を確認してください。';
        } finally {
            setBusy(false);
        }
    });
});
