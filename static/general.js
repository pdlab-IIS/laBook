function isbnValidate(isbn) {
    if (!isbn) return false;
    isbn = isbn.replace(/[-\s]/g, '');
    if (isbn.length !== 10 && isbn.length !== 13) return false;
    if (!/^\d+$/.test(isbn)) return false;
    if (isbn.length === 10) {
        let sum = 0;
        for (let i = 0; i < 9; i++) {
            sum += (i + 1) * parseInt(isbn[i], 10);
        }
        const checksum = isbn[9].toUpperCase() === 'X' ? 10 : parseInt(isbn[9], 10);
        sum += checksum;
        return sum % 11 === 0;
    } else if (isbn.length === 13) {
        let sum = 0;
        for (let i = 0; i < 12; i++) {
            sum += (i % 2 === 0 ? 1 : 3) * parseInt(isbn[i], 10);
        }
        const checksum = (10 - (sum % 10)) % 10;
        return checksum === parseInt(isbn[12], 10);
    }
    return false;
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