const nameKey = `pdlab_nickname`;

async function transferToEditPage(isbn) {
    const form = document.getElementById('manageBookForm');
    const mode = form.getAttribute('data-mode');
    if (mode !== 'edit' && await isBookExist(isbn)) {
        alert('Book already exists.\nRedirecting to manage page.');
        window.location.href = `/books/manage?isbn=${isbn}`;
        form.setAttribute('data-mode', 'edit');
        return true;
    }
    return false;
}

async function updateBook(info = true) {
    const isbnInput = document.getElementById('isbn');
    const manageBookForm = document.getElementById('manageBookForm');
    const itxTitle = document.getElementById('title');
    const isbn = isbnInput.value;
    if (!isbnValidate(isbn)) {
        alert('Invalid ISBN.\nPlease check and try again.');
        isbnInput.focus();
        return;
    }
    if (await transferToEditPage(isbn)) return;

    if (itxTitle.value == '') {
        alert('Title must be input');
        itxTitle.focus();
        return;
    }

    const formData = new FormData(manageBookForm);
    const data = {};
    formData.forEach((v, k) => data[k] = v);

    if (data.shelf_code) {
        try {
            const resp = await fetch(`/shelves/by_code/${encodeURIComponent(data.shelf_code)}`);
            if (resp.ok) {
                const shelf = await resp.json();
                data.shelf_id = shelf.shelf_id;
            } else {
                const createResp = await fetch('/shelves', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        shelf_code: data.shelf_code,
                        location_description: ''
                    })
                });
                if (createResp.ok) {
                    const shelf = await createResp.json();
                    data.shelf_id = shelf.shelf_id;
                } else {
                    alert('Failed to create shelf.');
                    return;
                }
            }
        } catch (e) {
            alert('Failed to resolve shelf code.');
            return;
        }
        delete data.shelf_code;
    } else data.shelf_id = null;

    let url, method;
    const mode = manageBookForm.getAttribute('data-mode');
    if (mode === 'edit') {
        url = `/books/${isbn}`;
        method = 'PUT';
    } else {
        url = '/books';
        method = 'POST';
    }

    const resp = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });

    if (resp.ok) {
        if (info) {
            alert('Book information updated successfully.');
            window.location.href = `/books/manage?isbn=` + isbn;
        }
        return true
    } else {
        const err = await resp.json();
        alert('Error: ' + (err.description || resp.statusText));
        return false;
    }
}

document.addEventListener('DOMContentLoaded', async function () {
    const isbnInput = document.getElementById('isbn');
    const manageBookForm = document.getElementById('manageBookForm');
    const shelfCodeInput = document.getElementById('shelf_code');
    const shelfIdInput = document.getElementById('shelf_id');
    const itxName = document.getElementById('itxName');
    const itxBorrower = document.getElementById('itxBorrower');
    const itxTime = document.getElementById('itxTime');
    const itxLoanId = document.getElementById('itxLoanId')
    const btnReturnBook = document.getElementById('btnReturnBook');
    const btnSubmitForm = document.getElementById('btnSubmitForm"');

    if (isbnInput.value == '0') {
        mobileScan();
    } else {
        isbnInput.focus();
    }

    itxName.value = localStorage.getItem(nameKey);

    if (!itxBorrower.value) {
        btnReturnBook.style.display = 'none';
    } else {
        try {
            const response = await fetch(`/loans/activeLoan/${isbnInput.value}`, {
                method: 'POST'
            });
            if (response.ok) {
                const loan = await response.json();
                if (loan) {
                    let loanDateStr = loan.loan_date;
                    // Only append 'Z' if not already present and no timezone info
                    if (!/Z$|[+-]\d{2}:?\d{2}$/.test(loanDateStr)) {
                        loanDateStr += 'Z';
                    }
                    const utcDate = new Date(loanDateStr);
                    const jstDate = new Date(utcDate.getTime());
                    const yyyy = jstDate.getFullYear();
                    const mm = String(jstDate.getMonth() + 1).padStart(2, '0');
                    const dd = String(jstDate.getDate()).padStart(2, '0');
                    const hh = String(jstDate.getHours()).padStart(2, '0');
                    const min = String(jstDate.getMinutes()).padStart(2, '0');
                    const ss = String(jstDate.getSeconds()).padStart(2, '0');
                    itxTime.value = `${yyyy}-${mm}-${dd} ${hh}:${min}:${ss}`;
                    itxLoanId.value = loan.loan_id;
                }
            }
        } catch (e) {
            console.error('Failed to fetch active loan:', e);
        }
    }

    if (shelfCodeInput && !shelfCodeInput.value && shelfIdInput && shelfIdInput.value && !isNaN(shelfIdInput.value)) {
        try {
            const resp = await fetch(`/shelves/${shelfIdInput.value}`);
            if (resp.ok) {
                const shelf = await resp.json();
                if (shelf.shelf_code) shelfCodeInput.value = shelf.shelf_code;
            }
        } catch (e) {
        }
    }

    manageBookForm.addEventListener('submit', async function (e) {
        e.preventDefault();
    });

    if (isbnInput && isbnInput.value) {
        loadReviews(isbnInput.value);
    }
});

function makeEAN13(input) {
    let s = String(input);
    if (/^97[89]\d{10}$/.test(s) || /^2\d{12}$/.test(s)) {
        return s;
    }

    const core9 = s.slice(0, 9);
    if (/^\d{9}$/.test(core9) && s.length === 10) {
        const ean12 = "978" + core9;
        let sum = 0;
        for (let i = 0; i < 12; i++) {
            const digit = Number(ean12[i]);
            sum += digit * ((i % 2 === 0) ? 1 : 3);
        }
        const checkDigit = (10 - (sum % 10)) % 10;
        return ean12 + String(checkDigit);
    }
    return s;
}

async function fetchBookInfo() {
    const btnFetch = document.getElementById('btnFetchBookInfo');
    const isbnInput = document.getElementById('isbn');
    let isbn = isbnInput.value;
    const spnFetch = document.getElementById('spnBtnFetchBookInfo');
    const commentInput = document.getElementById('comment');
    const isbnFormatted = makeEAN13(isbn);
    if (isbnFormatted != isbn) {
        isbn = isbnFormatted;
        if (await transferToEditPage(isbn)) return;
        isbnInput.value = "";
        if (!commentInput.value) commentInput.value = isbn;
        isbnInput.focus();
    }
    if (!isbnValidate(isbn)) {
        alert('invalid ISBN');
        isbnInput.focus();
        return;
    }
    if (await transferToEditPage(isbn)) return;
    try {

        btnFetch.disabled = true;
        spnFetch.innerHTML = '<i class="fas fa-spinner" ></i>';
        const response = await fetch(`/books/api/fetch_book_info/${isbn}`);
        btnFetch.disabled = false;
        spnFetch.innerHTML = '<i class="fas fa-globe" aria-hidden="true"></i>';
        if (!response.ok) {
            console.error('not found online:', e);
            return;
        }
        const book = await response.json();
        const titleInput = document.getElementById('title');
        if (titleInput.value == 'None') titleInput.value = '';
        if (titleInput && !titleInput.value) titleInput.value = book.title || '';

        const authorInput = document.getElementById('author');
        if (authorInput.value == 'None') authorInput.value = '';
        if (authorInput && !authorInput.value) authorInput.value = book.author || '';

        const publisherInput = document.getElementById('publisher');
        if (publisherInput.value == 'None') publisherInput.value = '';
        if (publisherInput && !publisherInput.value) publisherInput.value = book.publisher || '';

        const pubDateInput = document.getElementById('publication_date');
        if (pubDateInput && !pubDateInput.value) pubDateInput.value = book.publication_date || '';

        const coverPathInput = document.getElementById('cover_image_path');
        if (coverPathInput.value == 'None') coverPathInput.value = '';
        if (coverPathInput && !coverPathInput.value)
            coverPathInput.value = book.cover_image_path;

        const coverImg = document.getElementById('cover_preview');
        if (coverImg && book.cover_image_path) coverImg.src = '/' + book.cover_image_path;

    } catch (e) {
        console.error('fetch book info failed:', e);
    }
}

async function mobileScan() {
    const shelfCode = document.getElementById('shelf_code').value;
    const ngrokUrl = "https://pdlab.iis.u-tokyo.ac.jp/labook";

    window.location.href = `${ngrokUrl}/scan/${shelfCode}`;
}

async function deleteBook() {
    const isbn = document.getElementById('isbn').value;
    if (!isbnValidate(isbn)) {
        alert('Invalid ISBN.\nPlease check and try again.');
        return;
    }
    if (!confirm('Are you sure you want to delete this book?')) return;

    try {
        const response = await fetch(`/books/${isbn}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            alert('Book deleted successfully.');
            window.location.href = '/';
        } else {
            const err = await response.json();
            alert('Error: ' + (err.description || response.statusText));
        }
    } catch (e) {
        console.error('Delete book failed:', e);
        alert('Failed to delete book. Please try again later.');
    }
}

async function preLoanProcess() {
    if (!await updateBook(false)) return false;

    const itxName = document.getElementById('itxName');
    const name = itxName.value.trim();
    if (!name) {
        alert('Please enter your name.');
        itxName.focus();
        return false;
    }
    localStorage.setItem(nameKey, name);
    try {
        const resp = await fetch(`/users/by_name/${encodeURIComponent(name)}`);
        if (resp.ok) {
            const user = await resp.json();
            return user.user_id;
        } else {
            const createResp = await fetch('/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_name: name })
            });
            if (createResp.ok) {
                const user = await createResp.json();
                return user.user_id;
            } else {
                alert('Failed to create user.');
                return false;
            }
        }
    } catch (e) {
        alert('Failed to check user existence.');
        return false;
    }
}

async function returnBookMethod(user_id) {
    const itxLoanId = document.getElementById('itxLoanId')
    loan_id = itxLoanId.value;
    try {
        if (loan_id) {
            const responseUpdateLoan = await fetch(`/loans/${loan_id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ returner_id: user_id })
            });
            if (responseUpdateLoan.ok) {
                return true;
            } else {
                const err = await responseUpdateLoan.json();
                alert('Error: ' + (err.description || responseUpdateLoan.statusText));
            }
        } else {
            alert('Failed to return book.');
        }
    } catch (e) {
        console.error('Return book failed:', e);
        alert('Failed to return book.');
    }
    return false;
}

async function borrowBook() {
    user_id = await preLoanProcess();
    if (!user_id) return false;
    const isbn = document.getElementById('isbn').value;

    const btnReturnBook = document.getElementById('btnReturnBook');
    if (btnReturnBook.style.display !== 'none') {
        alert('Returning book before borrowing...');
        if (!await returnBookMethod(user_id)) {
            return false;
        }
    }
    const respLoan = await fetch(`/loans`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isbn: isbn, borrower_id: user_id })
    });
    if (respLoan.ok) {
        alert('Book < ' + document.getElementById('title').value + ' >\n is borrowed by < ' + document.getElementById('itxName').value + ' > successfully.');
        window.location.href = '/';
    } else {
        const err = await respLoan.json();
        alert('Error: ' + (err.description || respLoan.statusText));
        return false;
    }
}

async function returnBook() {
    user_id = await preLoanProcess();
    if (user_id === false) return false;

    if (await returnBookMethod(user_id)) {
        alert('Book < ' + document.getElementById('title').value + ' > \n is returned successfully.');
        window.location.href = '/';
    } else {
        return false;
    }
}

async function addToNotion() {
    const notionApiUrl = "/api/notion/add";

    const isbn = document.getElementById('isbn').value;
    const title = document.getElementById('title').value;
    const reviewer = document.getElementById('itxName').value;
    const review = document.getElementById('itxReview').value;

    if (!reviewer) {
        alert('Please enter your name.');
        document.getElementById('itxName').focus();
        return false;
    }
    if (!title) {
        alert('Title must not be blank.');
        document.getElementById('title').focus();
        return false;
    }
    if (!review) {
        alert('Please enter your review.');
        document.getElementById('itxReview').focus();
        return false;
    }

    const payload = { isbn, title, reviewer, review };

    try {
        const resp = await fetch(notionApiUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (resp.ok) {
            alert("Review added to Notion successfully!");
            window.location.reload()
        } else {
            const err = await resp.json();
            alert("Failed to add to Notion: " + (err.description || resp.statusText));
        }
    } catch (e) {
        alert("Error: " + e);
    }
}

async function loadReviews(isbn) {
    const tableBody = document.querySelector('#reviewTable tbody');
    tableBody.innerHTML = '<tr><td colspan="3">Loading...</td></tr>';
    try {
        const resp = await fetch(`/api/notion/get_review_by_isbn/${isbn}`);
        if (!resp.ok) {
            tableBody.innerHTML = '<tr><td colspan="3">Failed to load reviews</td></tr>';
            return;
        }
        const data = await resp.json();
        if (!Array.isArray(data) || data.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="3">No reviews found</td></tr>';
            return;
        }
        tableBody.innerHTML = '';
        data.forEach(entry => {
            const props = entry.properties || {};
            // Created Time
            let reviewCreated = entry.created_time || '';
            if (reviewCreated) {
                // ISO8601 → YYYY-MM-DD HH:mm
                const dt = new Date(reviewCreated);
                reviewCreated = dt.toLocaleString();
            }
            // Reviewer
            let reviewer = '';
            if (props.Reviewer && props.Reviewer.select && props.Reviewer.select.name)
                reviewer = props.Reviewer.select.name;
            // Review
            let review = '';
            if (props.Review && props.Review.rich_text && props.Review.rich_text.length > 0)
                review = props.Review.rich_text.map(rt => rt.plain_text).join('');

            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${reviewer} (${reviewCreated})</td><td>${review}</td>`;
            tableBody.appendChild(tr);
        });
    } catch (e) {
        tableBody.innerHTML = `<tr><td colspan="3">Error: ${e}</td></tr>`;
    }
}