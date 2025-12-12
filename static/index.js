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
const pageSize = 25;
let lastBooksCount = 0;
let totalBooksCount = 0;
let lastkey = "";

document.addEventListener('DOMContentLoaded', async function () {
    await loadAllShelves();

    const searchInput = document.getElementById('searchInput');
    const spnLockMode = document.getElementById('spnLockMode');
    const spnSpd = document.getElementById('spnSpd');

    if (window.location.href.includes("labook")) {
        spnSpd.innerHTML = `<spn title="You are in LOCAL mode now"><i class="fa-solid fa-gauge-high "></i></spn>`
    } else {
        spnSpd.innerHTML = `<a href="http://labook.local"><spn title="Change to LOCAL mode (Prototyping&DesignLab5G WiFi only. Also check that you are not using a VPN)"><i class="fa-solid fa-globe"></i></spn></a>`
    }

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

    searchInput.addEventListener('keydown', async function (e) {
        searchValue = searchInput.value;
        if (e.key === 'Enter') {
            if (lockModeLocation && isbnValidate(searchValue)) {
                if (await isBookExist(searchValue)) {
                    try {
                        const respUpdateBook = await fetch(`/books/move/${searchValue}`, {
                            method: 'PUT',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ shelf_code: lockModeLocation })
                        });
                        if (!respUpdateBook.ok) {
                            console.error('Error updating book:', respUpdateBook.statusText);
                            return;
                        }
                        const updatedBook = await respUpdateBook.json();
                        if (!updatedBook) {
                            console.error('No book data returned after update');
                            return;
                        }
                        console.log('Book updated successfully:', updatedBook);
                        searchInput.value = '';
                        musicRegister.play();
                        updateBooksTable();
                    } catch (err) {
                        console.error('Error updating book:', err);
                        return;
                    }
                } else {
                    let book = {};
                    try {
                        const respFetchBook = await fetch(`/books/api/fetch_book_info/${searchValue}`);
                        if (!respFetchBook.ok) {
                            console.error('Error fetching book:', respFetchBook.statusText);
                            musicAlert.play();
                            searchInput.select();
                            return;
                        }
                        const bookData = await respFetchBook.json();
                        if (!bookData) return;
                        if (!bookData.title) {
                            console.error('Book data is incomplete:', book);
                            musicAlert.play();
                            searchInput.select();
                            return;
                        }
                        book = {
                            isbn: bookData.isbn,
                            title: bookData.title,
                            author: bookData.author,
                            publisher: bookData.publisher,
                            publication_date: bookData.publication_date,
                            cover_image_path: bookData.cover_image_path,
                        };
                    } catch (err) {
                        console.error('Error processing book data:', err);
                        return;
                    }
                    try {
                        const respAddBook = await fetch(`/books`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                ...book,
                                shelf_code: lockModeLocation
                            })
                        });
                        if (respAddBook.ok) {
                            console.log('Book updated successfully:', book);
                            searchInput.value = '';
                            musicNewEntry.play();
                            updateBooksTable();
                        } else {
                            console.error('Error adding book:', respAddBook.statusText);
                        }
                    } catch (err) {
                        console.error('Error adding book:', err);
                    }
                }
            } else if (searchValue.startsWith(magicPrefix)) {
                let locationCode = searchValue.split('/').pop();
                lockModeLocation = locationCode;
                spnLockMode.innerHTML = '<font color="red"><i class="fa-solid fa-location-pin-lock"></i> ' + locationCode + '</font>';
                searchInput.value = '';
            } else {
                spnLockMode.innerHTML = '&emsp;';
                updateBooksTable();
            }
        }
    });

    document.getElementById('searchBtn').addEventListener('click', function () {
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
        renderIndicators();
        updateBooksTable();
    });
    document.getElementById('addBookBtn').addEventListener('click', function () {
        window.location.href = '/books/manage';
    });
    document.getElementById('spnLockMode').addEventListener('click', function () {
        searchInput.value = magicPrefix;
        lockModeLocation = null;
        searchInput.focus();
    });
    document.getElementById('btnScanner').addEventListener('click', function () {
        window.location.href = '/books/manage?isbn=0';
    });
    document.getElementById('prevPageBtn').addEventListener('click', function () {
        if (currentPage > 1) {
            currentPage--;
            updateBooksTable();
        }
    });
    document.getElementById('nextPageBtn').addEventListener('click', function () {
        if (lastBooksCount === pageSize) {
            currentPage++;
            updateBooksTable();
        }
    });

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
    const tableBody = document.querySelector('#booksTable tbody');
    const keyword = document.getElementById('searchInput').value.trim();
    if (lastkey != keyword) {
        currentPage = 1;
        lastkey = keyword;
    }
    const statusOnly = filterStatus;
    let books = [];
    let totalBooksCount = 0;

    if (controller) controller.abort();
    controller = new AbortController();
    const requestId = ++currentRequestId;

    if (statusOnly) {
        let url = `/books?sort=${sortKey}&order=${sortOrder}&limit=99999`;
        if (keyword) url += `&keyword=${encodeURIComponent(keyword)}`;
        try {
            const resp = await fetch(url, { signal: controller.signal, cache: 'no-store' });
            if (requestId !== currentRequestId) return;
            books = await resp.json();
            books = books.filter(book => book.status !== null && book.status !== undefined && book.status !== "");
            totalBooksCount = books.length;
        } catch {
            tableBody.innerHTML = '<tr><td colspan="7">Failed to load books</td></tr>';
            return;
        }
    } else {
        const offset = (currentPage - 1) * pageSize;
        let url = `/books?sort=${sortKey}&order=${sortOrder}&limit=${pageSize}&offset=${offset}`;
        if (keyword) url += `&keyword=${encodeURIComponent(keyword)}`;
        try {
            const resp = await fetch(url, { signal: controller.signal, cache: 'no-store' });
            if (requestId !== currentRequestId) return;
            const data = await resp.json();
            books = data.books || [];
            totalBooksCount = data.total_count || books.length;
            lastBooksCount = books.length;
        } catch {
            tableBody.innerHTML = '<tr><td colspan="7">Failed to load books</td></tr>';
            return;
        }
    }

    let pagedBooks = books;
    if (statusOnly) {
        const totalPages = Math.max(1, Math.ceil(totalBooksCount / pageSize));
        const startIdx = (currentPage - 1) * pageSize;
        pagedBooks = books.slice(startIdx, startIdx + pageSize);
        document.getElementById('pageInfo').textContent =
            `Page ${currentPage} / ${totalPages} (${startIdx + 1}-${startIdx + pagedBooks.length} of ${totalBooksCount})`;
        document.getElementById('prevPageBtn').style.display = (currentPage === 1) ? 'none' : '';
        document.getElementById('nextPageBtn').style.display = (currentPage >= totalPages) ? 'none' : '';
    } else {
        const totalPages = Math.max(1, Math.ceil(totalBooksCount / pageSize));
        const startEntry = totalBooksCount === 0 ? 0 : (currentPage - 1) * pageSize + 1;
        const endEntry = (currentPage - 1) * pageSize + books.length;
        document.getElementById('pageInfo').textContent =
            `Page ${currentPage} / ${totalPages} (${startEntry}-${endEntry} of ${totalBooksCount})`;
        document.getElementById('prevPageBtn').style.display = (currentPage === 1) ? 'none' : '';
        document.getElementById('nextPageBtn').style.display = (currentPage >= totalPages) ? 'none' : '';
    }

    tableBody.innerHTML = '';
    pagedBooks.forEach((book, idx) => {
        const tr = document.createElement('tr');
        const shelfCellId = `shelf-cell-${requestId}-${idx}`;
        tr.innerHTML = `
            <td class="clickable-cover" style="cursor:pointer;">
                <img src="${book.cover_image_path || '/static/book-solid.svg'}" alt="Cover Image" style="max-width: 60px; max-height: 100px;" />
            </td>
            <td class="clickable-title" style="cursor:pointer;"><a class='book-title'>${book.title || ''}</a></td>
            <td class="searchable-author" style="cursor:pointer">${book.author || ''}</td>
            <td class="searchable-publisher" style="cursor:pointer">${book.publisher || ''}</td>
            <td class="searchable-publication-date">${book.publication_date || ''}</td>
            <td class="searchable-shelf" id="${shelfCellId}" style="cursor:pointer">
                ${book.shelf_id && shelfCache[book.shelf_id]
                    ? shelfCache[book.shelf_id]
                    : '<i class="fa-solid fa-circle-question"></i>'}
            </td>
            ${book.status ? `<td class="searchable-borrower">${book.status}</td>` : `<td><i class="fa-solid fa-check"></i></td>`}
        `;
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
            if (book.shelf_id) {
                document.getElementById('searchInput').value = "shelf_id:" + String(book.shelf_id);
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
        tableBody.innerHTML = '<tr><td colspan="7">No books found</td></tr>';
    }
}

window.addEventListener('beforeunload', () => {
    if (controller) controller.abort();
});
