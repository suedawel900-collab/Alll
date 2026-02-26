const Telegram = window.Telegram.WebApp;
Telegram.ready();

// Get user ID from Telegram (in production, use initData)
// For testing, we'll prompt or use a dummy. In real, extract from initData.
let userId = null;
try {
    const initData = Telegram.initData;
    // Parse initData to get user id – simplified: we assume it's there.
    // Actually, Telegram.WebApp.initDataUnsafe.user.id
    userId = Telegram.initDataUnsafe.user.id;
} catch (e) {
    // Fallback for local testing
    userId = prompt("Enter your Telegram user ID") || "12345";
}

const CARD_COST = 10;           // must match backend
const MAX_CARDS = 20;
let selectedCards = [];         // list of card IDs (as integers)
let calledNumbers = new Set();
let balance = 0;
let roundPrize = 0;
let roundNumber = 0;
let activeGames = 0;

// DOM elements
const playerIdSpan = document.getElementById('player-id');
const walletSpan = document.getElementById('wallet');
const activeGamesSpan = document.getElementById('active-games');
const stakeSpan = document.getElementById('stake');
const activeGameSpan = document.getElementById('active-game');
const roundPrizeSpan = document.getElementById('round-prize');
const playersListDiv = document.getElementById('players-list');
const selectedCardsList = document.getElementById('selected-cards-list');
const totalCostSpan = document.getElementById('total-cost');
const confirmBtn = document.getElementById('confirm-btn');
const clearBtn = document.getElementById('clear-btn');
const addCardBtn = document.getElementById('add-card');
const cardInput = document.getElementById('card-input');
const numbersGrid = document.getElementById('numbers-grid');

playerIdSpan.textContent = userId;

// Fetch initial user data
async function fetchUserData() {
    const response = await fetch(`/get_user_data?user_id=${userId}`);
    const data = await response.json();
    balance = data.balance;
    activeGames = data.active_games;
    roundPrize = data.round_prize;
    roundNumber = data.round_number;
    updateStats();
}

function updateStats() {
    walletSpan.textContent = balance.toFixed(2) + ' ETB';
    activeGamesSpan.textContent = activeGames;
    const stake = selectedCards.length * CARD_COST;
    stakeSpan.textContent = stake.toFixed(2) + ' ETB';
    activeGameSpan.textContent = `Round ${roundNumber}`;
    roundPrizeSpan.textContent = roundPrize.toFixed(2) + ' ETB';
    confirmBtn.textContent = `Confirm (${stake.toFixed(2)} ETB)`;
    totalCostSpan.textContent = `Total: ${stake.toFixed(2)} ETB`;
}

// Called numbers grid (1-75)
function buildGrid() {
    let html = '';
    for (let row = 0; row < 5; row++) {
        html += '<tr>';
        for (let col = 0; col < 15; col++) {
            const num = row * 15 + col + 1;
            html += `<td id="num-${num}" class="${calledNumbers.has(num) ? 'called' : ''}">${num}</td>`;
        }
        html += '</tr>';
    }
    numbersGrid.innerHTML = html;
}

// Poll for called numbers
async function pollCalledNumbers() {
    const response = await fetch('/get_called_numbers');
    const data = await response.json();
    const newNumbers = data.called.filter(n => !calledNumbers.has(n));
    newNumbers.forEach(n => {
        calledNumbers.add(n);
        const cell = document.getElementById(`num-${n}`);
        if (cell) cell.classList.add('called');
    });
    // Also update round status if needed
    if (data.status === 'finished') {
        // Maybe reload page or show message
    }
}

// Add a card to selection
addCardBtn.addEventListener('click', () => {
    const cardId = parseInt(cardInput.value);
    if (isNaN(cardId)) return;
    if (selectedCards.length >= MAX_CARDS) {
        alert(`Max ${MAX_CARDS} cards`);
        return;
    }
    if (selectedCards.includes(cardId)) {
        alert('Card already selected');
        return;
    }
    selectedCards.push(cardId);
    renderSelectedCards();
    cardInput.value = '';
});

function renderSelectedCards() {
    selectedCardsList.innerHTML = '';
    selectedCards.forEach(id => {
        const li = document.createElement('li');
        li.innerHTML = `#${id} <span class="remove" data-id="${id}">❌</span>`;
        selectedCardsList.appendChild(li);
    });
    // Add remove event listeners
    document.querySelectorAll('.remove').forEach(span => {
        span.addEventListener('click', (e) => {
            const id = parseInt(e.target.dataset.id);
            selectedCards = selectedCards.filter(c => c !== id);
            renderSelectedCards();
            updateStats();
        });
    });
    updateStats();
}

// Clear all selected cards
clearBtn.addEventListener('click', () => {
    selectedCards = [];
    renderSelectedCards();
});

// Confirm purchase
confirmBtn.addEventListener('click', async () => {
    if (selectedCards.length === 0) {
        alert('Select at least one card');
        return;
    }
    const response = await fetch('/buy_cards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, card_ids: selectedCards })
    });
    const result = await response.json();
    if (result.success) {
        // Update balance and clear selection
        balance = result.new_balance;
        selectedCards = [];
        renderSelectedCards();
        updateStats();
        // Optionally refresh user data
        fetchUserData();
        Telegram.showPopup({ title: 'Success', message: 'Cards purchased!', buttons: [{type: 'ok'}] });
    } else {
        Telegram.showPopup({ title: 'Error', message: result.message, buttons: [{type: 'ok'}] });
    }
});

// Claim Bingo button – we'll add a separate button in the UI (maybe in stats)
// For simplicity, add a floating button or use a command.
// We'll add a "BINGO!" button in the header.
const bingoBtn = document.createElement('button');
bingoBtn.textContent = 'BINGO!';
bingoBtn.style.position = 'fixed';
bingoBtn.style.bottom = '20px';
bingoBtn.style.right = '20px';
bingoBtn.style.padding = '16px';
bingoBtn.style.background = '#f44336';
bingoBtn.style.color = 'white';
bingoBtn.style.border = 'none';
bingoBtn.style.borderRadius = '50px';
bingoBtn.style.fontSize = '18px';
bingoBtn.style.cursor = 'pointer';
bingoBtn.style.zIndex = 1000;
document.body.appendChild(bingoBtn);

bingoBtn.addEventListener('click', async () => {
    const response = await fetch('/claim_bingo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
    });
    const result = await response.json();
    Telegram.showPopup({
        title: result.success ? 'BINGO!' : 'Oops',
        message: result.message,
        buttons: [{type: 'ok'}]
    }, () => {
        if (result.success) {
            Telegram.close();
        }
    });
});

// Initialize
buildGrid();
fetchUserData();
setInterval(pollCalledNumbers, 2000);