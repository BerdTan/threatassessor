// Theme Toggle for ThreatAssessor Dashboard

document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle');
    const iconMoon = themeToggle.querySelector('.icon-moon');
    const iconSun  = themeToggle.querySelector('.icon-sun');

    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.body.className = `${savedTheme}-theme`;
    updateIcon(savedTheme);

    themeToggle.addEventListener('click', () => {
        const currentTheme = document.body.classList.contains('dark-theme') ? 'dark' : 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.body.className = `${newTheme}-theme`;
        localStorage.setItem('theme', newTheme);
        updateIcon(newTheme);
    });

    function updateIcon(theme) {
        if (theme === 'dark') {
            iconMoon.style.display = 'none';
            iconSun.style.display  = '';
        } else {
            iconSun.style.display  = 'none';
            iconMoon.style.display = '';
        }
    }
});
