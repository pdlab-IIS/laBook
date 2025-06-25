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
            window.location.reload();
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
                    itxTime.value = loan.loan_date;
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

    if (isbnInput.value == '0') {
        mobileScan();
    } else {
        isbnInput.focus();
    }
});

async function fetchBookInfo() {
    const btnFetch = document.getElementById('btnFetchBookInfo');
    const isbnInput = document.getElementById('isbn');
    const isbn = isbnInput.value;
    const spnFetch = document.getElementById('spnBtnFetchBookInfo');
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

