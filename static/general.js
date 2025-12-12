function isbnValidate(isbn) {
    if (!isbn) return false;
    isbn = isbn.replace(/[-\s]/g, '').toUpperCase();

    const is10 = /^[0-9]{10}$/.test(isbn);
    const is13 = /^[0-9]{13}$/.test(isbn);
    if (!is10 && !is13) return false;

    if (is10) {
        let sum = 0;
        for (let i = 0; i < 9; i++) {
            sum += (10 - i) * parseInt(isbn[i], 10);
        }
        let last = parseInt(isbn[9], 10);
        
        const checksum = (sum % 11);
        if (checksum === 1 && isbn[9] === '0') {
            return true;
        }
        if (checksum === 0) {
            return true;
        }
        return false;
    } else {
        let sum = 0;
        for (let i = 0; i < 12; i++) {
            const n = parseInt(isbn[i], 10);
            sum += n * (i % 2 === 0 ? 1 : 3);
        }
        const checksum = (10 - (sum % 10)) % 10;
        return checksum === parseInt(isbn[12], 10);
    }
}

async function isBookExist(isbn) {
    return fetch(`/books/${isbn}`)
        .then(resp => {
            if (resp.status === 404) return false;
            if (resp.ok) return true;
            throw new Error('Network error');
        });
}

function isUserExist(username) {
    if (!username) return false;
    return fetch(`/users/${username}`)
        .then(resp => {
            if (resp.status === 404) return false;
            if (resp.ok) return true;
            throw new Error('Network error');
        });
}