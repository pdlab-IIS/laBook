let currentSortKey = 'updatedtime';
let currentSortOrder = 'desc';
let filterStatus = false;
let lockModeLocation = null;
const musicRegister = new Audio('static/register.mp3');
const musicNewEntry = new Audio('static/newentry.mp3');
const musicAlert = new Audio('static/alert.mp3');
const magicPrefix = 'https://pdlab.iis.u-tokyo.ac.jp/L/';

let controller;
let currentRequestId = 0;

let currentPage = 1;
const pageSizeOptions = [10, 25, 50, 100];
let pageSize = readPageSize();
let totalBooksCount = 0;
let lastkey = "";

function readPageSize() {
    const match = document.cookie.match(/(?:^|;\s*)bookPageSize=(\d+)(?:;|$)/);
    const savedPageSize = Number(match?.[1]);
    return pageSizeOptions.includes(savedPageSize) ? savedPageSize : 25;
}

function savePageSize() {
    document.cookie = `bookPageSize=${pageSize}; path=/; max-age=31536000; SameSite=Lax`;
}

document.addEventListener('DOMContentLoaded', async function () {
    await loadAllShelves();

    const searchInput = document.getElementById('searchInput');
    const spnLockMode = document.getElementById('spnLockMode');
    const lockModeStatus = document.getElementById('lockModeStatus');
    const spnSpd = document.getElementById('spnSpd');
    const pageSizeBtn = document.getElementById('pageSizeBtn');
    const pageSizeStatus = document.getElementById('pageSizeStatus');
    const utilityMenu = document.getElementById('utilityMenu');
    const utilityMenuToggle = utilityMenu.querySelector('.utility-menu__toggle');
    const utilityMenuPanel = document.getElementById('utilityMenuPanel');
    const searchInputShell = document.getElementById('searchInputShell');
    const inventoryLocationBadge = document.getElementById('inventoryLocationBadge');
    const inventoryLocationText = document.getElementById('inventoryLocationText');
    const inventoryLocationModal = document.getElementById('inventoryLocationModal');
    const inventoryLocationForm = document.getElementById('inventoryLocationForm');
    const inventoryLocationInput = document.getElementById('inventoryLocationInput');
    const inventoryIsbnMessage = document.getElementById('inventoryIsbnMessage');
    const inventoryProcessing = document.getElementById('inventoryProcessing');
    const inventoryProcessingText = document.getElementById('inventoryProcessingText');
    const searchBtn = document.getElementById('searchBtn');

    function setInventoryIsbnMessage(message = '', result = '') {
        inventoryIsbnMessage.textContent = message;
        inventoryIsbnMessage.hidden = !message;
        inventoryIsbnMessage.classList.toggle('is-invalid', result === 'invalid');
        inventoryIsbnMessage.classList.toggle('is-success', result === 'success');
        inventoryIsbnMessage.classList.toggle('is-unknown', result === 'unknown');
        searchInput.setAttribute('aria-invalid', result === 'invalid' ? 'true' : 'false');
    }

    function validateInventoryIsbnInput() {
        const normalizedIsbn = searchInput.value.trim().replace(/[-\s]/g, '').toUpperCase();
        if (!isbnValidate(normalizedIsbn)) {
            setInventoryIsbnMessage(
                'invalid / 無効: ISBN-10またはISBN-13を入力してください。',
                'invalid'
            );
            searchInput.select();
            return null;
        }

        setInventoryIsbnMessage();
        return normalizedIsbn;
    }

    function setInventoryProcessing(active, isbn = '') {
        inventoryProcessing.hidden = !active;
        inventoryProcessingText.textContent = active
            ? `棚卸し処理中: ${isbn}`
            : '棚卸し処理中...';
        searchInput.disabled = active;
        searchBtn.disabled = active;
        searchInputShell.setAttribute('aria-busy', String(active));
    }

    function rememberShelf(result, fallbackLocation) {
        const shelfId = Number(result && result.shelf_id);
        const shelfCode = (result && result.shelf_code) || fallbackLocation;
        if (Number.isInteger(shelfId) && shelfId > 0 && shelfCode) {
            shelfCache[shelfId] = shelfCode;
        }
    }

    async function processInventoryIsbn(isbn) {
        const inventoryLocation = lockModeLocation;
        setInventoryIsbnMessage();
        setInventoryProcessing(true, isbn);

        try {
            if (await isBookExist(isbn)) {
                const response = await fetch(`/books/move/${isbn}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ shelf_code: inventoryLocation })
                });
                if (!response.ok) {
                    throw new Error(`Book move failed with status ${response.status}`);
                }

                const result = await response.json();
                rememberShelf(result, inventoryLocation);
                searchInput.value = '';
                setInventoryIsbnMessage(
                    `success / 成功: ${isbn} を Location ${inventoryLocation} に登録しました。`,
                    'success'
                );
                musicRegister.play();
                await updateBooksTable();
                return;
            }

            const metadataResponse = await fetch(`/books/api/fetch_book_info/${isbn}`);
            if (!metadataResponse.ok) {
                throw new Error(`Book metadata lookup failed with status ${metadataResponse.status}`);
            }

            const bookData = await metadataResponse.json();
            if (!bookData || !bookData.title) {
                setInventoryIsbnMessage(
                    'unknown / 書誌情報なし: ISBNは有効ですが、書誌検索にヒットしませんでした。',
                    'unknown'
                );
                musicAlert.play();
                return;
            }

            const addResponse = await fetch('/books', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    isbn: bookData.isbn,
                    title: bookData.title,
                    author: bookData.author,
                    publisher: bookData.publisher,
                    publication_date: bookData.publication_date,
                    cover_image_path: bookData.cover_image_path,
                    shelf_code: inventoryLocation
                })
            });
            if (!addResponse.ok) {
                throw new Error(`Book add failed with status ${addResponse.status}`);
            }

            const result = await addResponse.json();
            rememberShelf(result, inventoryLocation);
            searchInput.value = '';
            setInventoryIsbnMessage(
                `success / 成功: ${isbn} を Location ${inventoryLocation} に追加しました。`,
                'success'
            );
            musicNewEntry.play();
            await updateBooksTable();
        } catch (error) {
            console.error('Inventory processing failed:', error);
            setInventoryIsbnMessage(
                'error / エラー: 棚卸し処理に失敗しました。もう一度お試しください。',
                'invalid'
            );
            musicAlert.play();
        } finally {
            setInventoryProcessing(false);
            searchInput.focus();
            if (searchInput.value) searchInput.select();
        }
    }

    function setLockModeStatus(active = false, detail = '') {
        lockModeStatus.textContent = active ? 'ON' : 'OFF';
        lockModeStatus.title = detail;
        spnLockMode.classList.toggle('is-active', active);
        searchInputShell.classList.toggle('is-inventory-mode', active);
        inventoryLocationText.textContent = active ? detail : '';
        inventoryLocationBadge.hidden = !active;
        if (!active) {
            setInventoryIsbnMessage();
        }
    }

    function closeUtilityMenu() {
        utilityMenuPanel.hidden = true;
        utilityMenuToggle.setAttribute('aria-expanded', 'false');
    }

    function openInventoryLocationModal() {
        inventoryLocationInput.value = lockModeLocation || '';
        inventoryLocationInput.setCustomValidity('');
        closeUtilityMenu();
        inventoryLocationModal.hidden = false;
        inventoryLocationInput.focus();
        inventoryLocationInput.select();
    }

    function closeInventoryLocationModal() {
        inventoryLocationModal.hidden = true;
        searchInput.focus();
    }

    function renderAccessMode() {
        const status = spnSpd.querySelector('.utility-menu__status');

        if (window.location.href.includes('labook')) {
            status.textContent = 'LOCAL';
            spnSpd.title = 'You are in LOCAL mode now';
            spnSpd.disabled = true;
            return;
        }

        status.textContent = 'REMOTE';
        spnSpd.title = 'Change to LOCAL mode (Prototyping&DesignLab5G WiFi only. Also check that you are not using a VPN)';
        spnSpd.disabled = false;
    }

    const initialShelfFilter = (window.initialShelfFilter || '').trim();
    if (initialShelfFilter) {
        searchInput.value = initialShelfFilter;
    }

    renderAccessMode();
    pageSizeStatus.textContent = String(pageSize);

    utilityMenuToggle.addEventListener('click', function () {
        const willOpen = utilityMenuPanel.hidden;
        utilityMenuPanel.hidden = !willOpen;
        utilityMenuToggle.setAttribute('aria-expanded', String(willOpen));
    });
    utilityMenu.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeUtilityMenu();
            utilityMenuToggle.focus();
        }
    });
    document.addEventListener('click', function (e) {
        if (!utilityMenuPanel.hidden && !utilityMenu.contains(e.target)) {
            closeUtilityMenu();
        }
    });

    const headers = Array.from(document.querySelectorAll('#booksTable thead th[data-key]'))
        .map(th => ({
            th,
            key: th.dataset.key,
            indicator: th.querySelector('.indicator')
        }));

    function renderIndicators() {
        headers.forEach(({ key, indicator }) => {
            indicator.innerHTML = '';
            if (key === 'status') {
                indicator.innerHTML = filterStatus
                    ? '<i class="fas fa-check-square" aria-hidden="true"></i>'
                    : '<i class="far fa-square" aria-hidden="true"></i>';
            }
            else if (currentSortKey === key) {
                indicator.innerHTML = currentSortOrder === 'asc'
                    ? '<i class="fa-solid fa-arrow-up-short-wide"></i>'
                    : '<i class="fa-solid fa-arrow-down-wide-short"></i>';
            } else {
                indicator.innerHTML = '<i class="fas fa-sort" aria-hidden="true" style="font-size: 0.75em;"></i>';
            }
        });
    }

    headers.forEach(({ th, key }) => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
            if (key === 'status') {
                filterStatus = !filterStatus;
                currentPage = 1;
            } else {
                if (currentSortKey === key) {
                    currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
                    if (!currentSortOrder) currentSortKey = null;
                } else {
                    currentSortKey = key;
                    currentSortOrder = 'asc';
                }
            }

            renderIndicators();
            updateBooksTable();
        });
    });

    searchInput.addEventListener('input', function () {
        setInventoryIsbnMessage();
    });
    searchInput.addEventListener('keydown', async function (e) {
        searchValue = searchInput.value.trim();
        if (e.key === 'Enter') {
            if (lockModeLocation) {
                e.preventDefault();
                const normalizedIsbn = validateInventoryIsbnInput();
                if (!normalizedIsbn) {
                    return;
                }
                await processInventoryIsbn(normalizedIsbn);
            } else if (searchValue.startsWith(magicPrefix)) {
                const locationCode = searchValue.split('/').pop().trim();
                if (!locationCode) {
                    openInventoryLocationModal();
                    return;
                }
                lockModeLocation = locationCode;
                setLockModeStatus(true, lockModeLocation);
                searchInput.value = '';
            } else {
                if (!lockModeLocation) {
                    setLockModeStatus();
                }
                updateBooksTable();
            }
        }
    });

    searchBtn.addEventListener('click', async function () {
        if (lockModeLocation) {
            const normalizedIsbn = validateInventoryIsbnInput();
            if (!normalizedIsbn) {
                return;
            }
            await processInventoryIsbn(normalizedIsbn);
            return;
        }
        currentPage = 1;
        updateBooksTable();
    });
    document.getElementById('resetBtn').addEventListener('click', function () {
        currentPage = 1;
        document.getElementById('searchInput').value = '';
        currentSortKey = 'updatedtime';
        currentSortOrder = 'desc';
        filterStatus = false;
        lockModeLocation = null;
        setLockModeStatus();
        renderIndicators();
        updateBooksTable();
        closeUtilityMenu();
    });
    document.getElementById('addBookBtn').addEventListener('click', function () {
        window.location.href = '/books/manage';
    });
    document.getElementById('manageUsersBtn').addEventListener('click', function () {
        window.location.href = this.dataset.url;
    });
    pageSizeBtn.addEventListener('click', function () {
        const currentIndex = pageSizeOptions.indexOf(pageSize);
        pageSize = pageSizeOptions[(currentIndex + 1) % pageSizeOptions.length];
        pageSizeStatus.textContent = String(pageSize);
        savePageSize();
        currentPage = 1;
        updateBooksTable();
    });
    spnSpd.addEventListener('click', function () {
        if (!spnSpd.disabled) {
            window.location.href = 'http://labook.local';
        }
    });
    document.getElementById('spnLockMode').addEventListener('click', function () {
        openInventoryLocationModal();
    });
    inventoryLocationForm.addEventListener('submit', function (e) {
        e.preventDefault();
        const location = inventoryLocationInput.value.trim();
        if (!location) {
            inventoryLocationInput.setCustomValidity('Locationを入力してください');
            inventoryLocationInput.reportValidity();
            return;
        }

        lockModeLocation = location;
        setLockModeStatus(true, lockModeLocation);
        setInventoryIsbnMessage();
        searchInput.value = '';
        closeInventoryLocationModal();
    });
    inventoryLocationInput.addEventListener('input', function () {
        inventoryLocationInput.setCustomValidity('');
    });
    document.getElementById('inventoryLocationCancel').addEventListener('click', function () {
        closeInventoryLocationModal();
    });
    inventoryLocationModal.addEventListener('click', function (e) {
        if (e.target === inventoryLocationModal) {
            closeInventoryLocationModal();
        }
    });
    inventoryLocationModal.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeInventoryLocationModal();
        }
    });
    document.getElementById('btnScanner').addEventListener('click', function () {
        window.location.href = '/books/manage?isbn=0';
    });
    document.querySelectorAll('[data-page-action="prev"]').forEach(button => button.addEventListener('click', function () {
        if (currentPage > 1) {
            currentPage--;
            updateBooksTable();
        }
    }));
    document.querySelectorAll('[data-page-action="next"]').forEach(button => button.addEventListener('click', function () {
        if (currentPage * pageSize < totalBooksCount) {
            currentPage++;
            updateBooksTable();
        }
    }));

    renderIndicators();
    updateBooksTable();  
    searchInput.focus();
});


let shelfCache = {}; 
async function loadAllShelves() {
    try {
        const resp = await fetch('/shelves');
        if (!resp.ok) return;
        const shelves = await resp.json();
        shelves.forEach(shelf => {
            shelfCache[shelf.shelf_id] = shelf.shelf_code;
        });
    } catch (e) {
        console.error('Failed to load shelves:', e);
    }
}

async function updateBooksTable(sortKey = currentSortKey, sortOrder = currentSortOrder) {
    window.bulkEdit?.reset();
    const booksTable = document.getElementById('booksTable');
    const loadingIndicator = document.getElementById('bookListLoading');
    const tableBody = document.querySelector('#booksTable tbody');
    const keyword = document.getElementById('searchInput').value.trim();
    if (lastkey != keyword) {
        currentPage = 1;
        lastkey = keyword;
    }
    const statusOnly = filterStatus;
    let books = [];

    if (controller) controller.abort();
    controller = new AbortController();
    const requestId = ++currentRequestId;
    const loadingStartedAt = performance.now();
    loadingIndicator.hidden = false;
    booksTable.setAttribute('aria-busy', 'true');

    const offset = (currentPage - 1) * pageSize;
    let url = `/books?sort=${sortKey}&order=${sortOrder}&limit=${pageSize}&offset=${offset}`;
    if (keyword) url += `&keyword=${encodeURIComponent(keyword)}`;
    if (statusOnly) url += '&status=borrowed';
    try {
        const resp = await fetch(url, { signal: controller.signal, cache: 'no-store' });
        if (requestId !== currentRequestId) return;
        if (!resp.ok) throw new Error(`Book list failed with status ${resp.status}`);
        const data = await resp.json();
        if (requestId !== currentRequestId) return;
        books = data.books || [];
        totalBooksCount = data.total_count ?? books.length;
    } catch (error) {
        if (error.name === 'AbortError' || requestId !== currentRequestId) return;
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 8;
        cell.textContent = 'Failed to load books';
        row.appendChild(cell);
        tableBody.replaceChildren(row);
        return;
    } finally {
        if (requestId === currentRequestId) {
            const minimumVisibleMs = 300;
            const remainingMs = minimumVisibleMs - (performance.now() - loadingStartedAt);
            if (remainingMs > 0) {
                await new Promise(resolve => setTimeout(resolve, remainingMs));
            }
        }
        if (requestId === currentRequestId) {
            loadingIndicator.hidden = true;
            booksTable.removeAttribute('aria-busy');
        }
    }

    if (requestId !== currentRequestId) return;
    const pagedBooks = books;
    const totalPages = Math.max(1, Math.ceil(totalBooksCount / pageSize));
    const startEntry = totalBooksCount === 0 ? 0 : (currentPage - 1) * pageSize + 1;
    const endEntry = (currentPage - 1) * pageSize + books.length;
    document.querySelectorAll('[data-page-info]').forEach(info => {
        info.textContent = `Page ${currentPage} / ${totalPages} (${startEntry}-${endEntry} of ${totalBooksCount})`;
    });
    document.querySelectorAll('[data-page-action="prev"]').forEach(button => {
        button.disabled = currentPage <= 1;
    });
    document.querySelectorAll('[data-page-action="next"]').forEach(button => {
        button.disabled = currentPage >= totalPages;
    });

    tableBody.replaceChildren();
    pagedBooks.forEach((book, idx) => {
        const tr = document.createElement('tr');
        const selectionCell = document.createElement('td');
        selectionCell.className = 'book-selection';
        selectionCell.hidden = !window.bulkEdit?.active;
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.dataset.bookIsbn = String(book.isbn);
        checkbox.setAttribute('aria-label', `${book.title || book.isbn} を選択`);
        selectionCell.appendChild(checkbox);
        const shelfCellId = `shelf-cell-${requestId}-${idx}`;
        const coverSrc = book.cover_image_path
          ? (book.cover_image_path.startsWith('/') ? book.cover_image_path : `/${book.cover_image_path}`)
          : '/static/book-solid.svg';

        const coverCell = document.createElement('td');
        coverCell.className = 'clickable-cover';
        coverCell.style.cursor = 'pointer';
        const coverImage = document.createElement('img');
        coverImage.src = coverSrc;
        coverImage.alt = 'Cover Image';
        coverImage.style.maxWidth = '60px';
        coverImage.style.maxHeight = '100px';
        coverCell.appendChild(coverImage);

        const titleCell = document.createElement('td');
        titleCell.className = 'clickable-title';
        titleCell.style.cursor = 'pointer';
        const title = document.createElement('a');
        title.className = 'book-title';
        title.textContent = book.title || '';
        const compactMeta = document.createElement('span');
        compactMeta.className = 'book-compact-meta';
        compactMeta.textContent = [book.publisher, book.publication_date]
            .filter(Boolean)
            .join(' · ');
        const compactAuthor = document.createElement('span');
        compactAuthor.className = 'book-compact-author';
        compactAuthor.textContent = book.author || '';
        titleCell.append(title, compactAuthor, compactMeta);

        const authorCell = document.createElement('td');
        authorCell.className = 'searchable-author';
        authorCell.style.cursor = 'pointer';
        authorCell.textContent = book.author || '';

        const publisherCell = document.createElement('td');
        publisherCell.className = 'searchable-publisher';
        publisherCell.style.cursor = 'pointer';
        publisherCell.textContent = book.publisher || '';

        const publicationCell = document.createElement('td');
        publicationCell.className = 'searchable-publication-date';
        publicationCell.textContent = book.publication_date || '';

        const shelfCell = document.createElement('td');
        shelfCell.className = 'searchable-shelf';
        shelfCell.id = shelfCellId;
        shelfCell.style.cursor = 'pointer';
        if (book.shelf_id && shelfCache[book.shelf_id]) {
            shelfCell.textContent = shelfCache[book.shelf_id];
        } else {
            const unknownShelfIcon = document.createElement('i');
            unknownShelfIcon.className = 'fa-solid fa-circle-question';
            shelfCell.appendChild(unknownShelfIcon);
        }

        const statusCell = document.createElement('td');
        statusCell.className = 'clickable-status';
        if (book.status) {
            statusCell.classList.add('searchable-borrower');
            statusCell.textContent = book.status;
        } else {
            const availableIcon = document.createElement('i');
            availableIcon.className = 'fa-solid fa-check';
            statusCell.appendChild(availableIcon);
        }

        tr.append(
            selectionCell,
            coverCell,
            titleCell,
            authorCell,
            publisherCell,
            publicationCell,
            shelfCell,
            statusCell
        );
        tr.querySelector('.clickable-cover')?.addEventListener('click', function () {
            if (book.isbn) {
                window.location.href = `/books/manage?isbn=${encodeURIComponent(book.isbn)}`;
            }
        });
        tr.querySelector('.clickable-title')?.addEventListener('click', function () {
            if (book.isbn) {
                window.location.href = `/books/manage?isbn=${encodeURIComponent(book.isbn)}`;
            }
        });
        tr.querySelector('.searchable-author')?.addEventListener('click', function () {
            if (book.author) {
                document.getElementById('searchInput').value = book.author;
                updateBooksTable();
            }
        });
        tr.querySelector('.searchable-publisher')?.addEventListener('click', function () {
            if (book.publisher) {
                document.getElementById('searchInput').value = book.publisher;
                updateBooksTable();
            }
        });
        tr.querySelector('.searchable-shelf')?.addEventListener('click', function () {
            if (book.shelf_id && shelfCache[book.shelf_id]) {
                document.getElementById('searchInput').value = shelfCache[book.shelf_id];
                updateBooksTable();
            }
        });
        tr.querySelector('.clickable-status')?.addEventListener('click', function () {
            if (book.status) {
                updateBooksTable();
            }
        });
        tableBody.appendChild(tr);
    });
    if (pagedBooks.length === 0) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 8;
        cell.textContent = 'No books found';
        row.appendChild(cell);
        tableBody.replaceChildren(row);
    }
    window.bulkEdit?.sync();
}

window.addEventListener('beforeunload', () => {
    if (controller) controller.abort();
});
