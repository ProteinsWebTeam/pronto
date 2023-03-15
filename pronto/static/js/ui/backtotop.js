export function backToTop() {
    // Create a button element
    const button = document.createElement('button')
    button.innerHTML = '<i class="arrow up fitted icon"></i>';
    button.className = 'ui primary compact button';
    button.id = 'top-btn';

    button.addEventListener('click', e => {
        // When the user clicks on the button, scroll to the top of the document
        document.body.scrollTop = 0; // For Safari
        document.documentElement.scrollTop = 0; // For Chrome, Firefox, IE and Opera
    });

    document.body.appendChild(button);

    // When the user scrolls down 100px from the top of the document, show the button
    window.onscroll = () => {
        // When the user scrolls down 100px from the top of the document, show the button
        if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
            document.getElementById("top-btn").style.display = "block";
        } else {
            document.getElementById("top-btn").style.display = "none";
        }
    };
}

