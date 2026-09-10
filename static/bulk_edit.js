document.addEventListener('DOMContentLoaded', () => {
    const table = document.getElementById('booksTable');
    const all = document.getElementById('selectPageBooks');
    const launch = document.getElementById('bulkEditBtn');
    const dialog = document.getElementById('bulkEditDialog');
    const form = document.getElementById('bulkEditForm');
    const locationMode = document.getElementById('bulkLocationMode');
    const location = document.getElementById('bulkLocation');
    const ownerMode = document.getElementById('bulkOwnerMode');
    const owner = document.getElementById('bulkOwner');
    const save = document.getElementById('bulkEditSave');
    const cancel = document.getElementById('bulkEditCancel');
    const message = document.getElementById('bulkEditMessage');
    let busy = false;
    let active = false;
    let ownerReady = false;
    let selection = [];
    let generation = 0;
    const boxes = () => Array.from(table.querySelectorAll('[data-book-isbn]'));
    const desktopAvailable = () => getComputedStyle(launch).getPropertyValue('--bulk-available').trim() === '1';
    const responsiveObserver = new ResizeObserver(() => {
        if (!desktopAvailable() && active) {
            active = false;
            document.body.classList.remove('bulk-edit-active');
            boxes().forEach(box => { box.checked = false; });
            dialog.close();
            sync();
        }
    });
    responsiveObserver.observe(document.body);

    function sync() {
        const rows = boxes();
        const selected = rows.filter(box => box.checked).length;
        table.querySelectorAll('.book-selection').forEach(cell => { cell.hidden = !active; });
        rows.forEach(box => { box.disabled = !active || busy || table.hasAttribute('aria-busy'); });
        selection = rows.filter(box => box.checked).map(box => box.dataset.bookIsbn);
        all.disabled = !active || busy || !rows.length || table.hasAttribute('aria-busy');
        all.checked = rows.length > 0 && selected === rows.length;
        all.indeterminate = selected > 0 && selected < rows.length;
        launch.disabled = busy;
        launch.setAttribute('aria-pressed', String(active));
        document.getElementById('bulkEditSummary').textContent = `${selected}冊を選択中です。一覧のチェックボックスで対象を選択してください。`;
        fields();
    }
    window.bulkEdit = {
        get active() { return active; },
        sync,
        reset() {
            boxes().forEach(box => { box.checked = false; box.disabled = true; });
            all.checked = false;
            all.indeterminate = false;
            all.disabled = true;
            selection = [];
            launch.disabled = busy;
            document.getElementById('bulkEditSummary').textContent = '0冊を選択中です。一覧の更新後に対象を選択してください。';
            fields();
        }
    };
    table.addEventListener('change', event => {
        if (event.target === all) boxes().forEach(box => { if (!box.disabled) box.checked = all.checked; });
        sync();
    });
    function fields() {
        location.disabled = busy || locationMode.value !== 'set';
        location.required = locationMode.value === 'set';
        owner.disabled = busy || ownerMode.value !== 'set' || !ownerReady;
        owner.required = ownerMode.value === 'set';
        save.disabled = !active || !selection.length || busy || table.hasAttribute('aria-busy') || (locationMode.value === 'keep' && ownerMode.value === 'keep')
            || (ownerMode.value === 'set' && !ownerReady);
        locationMode.disabled = ownerMode.disabled = cancel.disabled = busy;
    }
    locationMode.addEventListener('change', fields);
    ownerMode.addEventListener('change', fields);
    launch.addEventListener('click', async () => {
        if (!desktopAvailable() || busy) return;
        document.getElementById('utilityMenuPanel').hidden = true;
        document.getElementById('utilityMenuToggle').setAttribute('aria-expanded', 'false');
        if (active) { locationMode.focus(); return; }
        active = true;
        document.body.classList.add('bulk-edit-active');
        const current = ++generation;
        form.reset();
        owner.replaceChildren(new Option('Ownerを選択', ''));
        ownerReady = false;
        message.textContent = 'Owner候補を読み込み中…';
        document.getElementById('utilityMenuPanel').hidden = true;
        document.getElementById('utilityMenuToggle').setAttribute('aria-expanded', 'false');
        sync();
        dialog.show();
        locationMode.focus();
        try {
            const response = await fetch('/users', {cache: 'no-store'});
            if (!response.ok) throw new Error();
            const users = await response.json();
            if (current !== generation || !dialog.open) return;
            users.filter(user => user.can_own_books === 1).forEach(user => {
                owner.add(new Option(user.name, String(user.user_id)));
            });
            ownerReady = true;
            message.textContent = '';
        } catch (_) {
            if (current !== generation || !dialog.open) return;
            message.textContent = 'Owner候補を取得できません。Locationのみの変更・Ownerの解除は可能です。';
        }
        fields();
    });
    cancel.addEventListener('click', () => dialog.close());
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => {
        ++generation;
        active = false;
        document.body.classList.remove('bulk-edit-active');
        boxes().forEach(box => { box.checked = false; });
        sync();
        document.getElementById('utilityMenuToggle').focus();
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!desktopAvailable() || busy || save.disabled || !form.reportValidity()) return;
        const payload = {isbns: [...selection]};
        if (locationMode.value === 'set') {
            if (!location.value.trim()) { message.textContent = 'Locationを入力してください。'; return; }
            payload.location = location.value.trim();
        } else if (locationMode.value === 'clear') payload.location = null;
        if (ownerMode.value === 'set') payload.owner_id = owner.value;
        else if (ownerMode.value === 'clear') payload.owner_id = null;
        const locationSummary = locationMode.value === 'set' ? payload.location
            : locationMode.value === 'clear' ? '未設定にする' : '変更しない';
        const ownerSummary = ownerMode.value === 'set' ? owner.selectedOptions[0].textContent
            : ownerMode.value === 'clear' ? '未設定にする' : '変更しない';
        if (!window.confirm(
            `${payload.isbns.length}冊を一括変更します。\n\nLocation: ${locationSummary}\nOwner: ${ownerSummary}\n\nこの内容で実行しますか？`
        )) return;
        busy = true;
        sync();
        message.textContent = '変更中…';
        let applied = false;
        try {
            const response = await fetch('/books/bulk', {
                method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (!response.ok) { message.textContent = result.description || '変更できませんでした。'; return; }
            applied = true;
            document.getElementById('bulkEditResult').textContent = `${result.updated_count}冊を変更しました。`;
            dialog.close();
            await loadAllShelves();
            await updateBooksTable();
        } catch (_) {
            if (applied) {
                document.getElementById('bulkEditResult').textContent = '一括変更は完了しました。一覧を再読み込みしてください。';
            } else {
                message.textContent = '変更結果を確認できません。再送前に閉じて一覧を更新し、結果を確認してください。';
            }
        } finally {
            busy = false;
            sync();
        }
    });
    sync();
});
