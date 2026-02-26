const Telegram = window.Telegram.WebApp;
Telegram.ready();

// Get user ID from Telegram
let userId = null;
try {
    userId = Telegram.initDataUnsafe.user.id;
} catch (e) {
    userId = prompt("Enter your Telegram user ID") || "12345";
}

const CARD_COST = 10;
const MAX_CARDS = 20;
let selectedCards = [];
let calledNumbers = new Set();
let balance = 0;
let roundPrize = 0;
let roundNumber = 0;
let activeGames = 0;
let roundStatus = 'waiting';
let myCards = []; // array of {id, board}

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
const cardsContainer = document.getElementById('cards-container');
const roundStatusDiv = document.getElementById('round-status-message');
const chooseCardsSection = document.getElementById('choose-cards-section');

playerIdSpan.textContent = userId;

// Fetch initial user data
async function fetchUserData() {
    const response = await fetch(`/get_user_data?user_id=${userId}`);
    const data = await response.json();
    balance = data.balance;
    activeGames = data.active_games;
    roundPrize = data.round_prize;
    roundNumber = data.round_number;
    roundStatus = data.round_status;
    updateStats();
    updateUIBasedOnRoundStatus();
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

function updateUIBasedOnRoundStatus() {
    const isWaiting = roundStatus === 'waiting';
    // Show/hide card selection section
    chooseCardsSection.style.display = isWaiting ? 'block' : 'none';
    // Update status message
    if (roundStatus === 'active') roundStatusDiv.textContent = '🔴 Round in progress – card selection disabled';
    else if (roundStatus === 'finished') roundStatusDiv.textContent = '✅ Round finished – wait for next round';
    else roundStatusDiv.textContent = '🟢 Select your cards';
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

// Poll for called numbers and round status
async function pollCalledNumbers() {
    const response = await fetch('/get_called_numbers');
    const data = await response.json();
    const newNumbers = data.called.filter(n => !calledNumbers.has(n));
    newNumbers.forEach(n => {
        calledNumbers.add(n);
        const cell = document.getElementById(`num-${n}`);
        if (cell) cell.classList.add('called');
    });
    // Update round status if changed
    if (data.status !== roundStatus) {
        roundStatus = data.status;
        fetchUserData();
        updateUIBasedOnRoundStatus();
        // If round became active/finished, refresh cards to update markings
        fetchMyCards();
    }
    // Update card markings if we have cards
    if (myCards.length > 0) {
        renderMyCards();
    }
}

// Fetch user's purchased cards for current round
async function fetchMyCards() {
    const response = await fetch(`/get_my_cards?user_id=${userId}`);
    const data = await response.json();
    myCards = data.cards;
    renderMyCards();
}

// Render each card as a small 5x5 grid
function renderMyCards() {
    if (!cardsContainer) return;
    if (myCards.length === 0) {
        cardsContainer.innerHTML = '<p>You have no cards in this round.</p>';
        return;
    }
    let html = '<div class="cards-container">';
    myCards.forEach(card => {
        html += `<div class="card-board">`;
        html += `<table>`;
        for (let r = 0; r < 5; r++) {
            html += '<tr>';
            for (let c = 0; c < 5; c++) {
                const cell = card.board[r][c];
                const isMarked = cell === 'FREE' || calledNumbers.has(cell);
                html += `<td class="${isMarked ? 'marked' : ''}">${cell}</td>`;
            }
            html += '</tr>';
        }
        html += `</table>`;
        html += `<div class="card-id">#${card.id}</div>`;
        html += `</div>`;
    });
    html += '</div>';
    cardsContainer.innerHTML = html;
}

// Add a card to selection (only when round waiting)
addCardBtn.addEventListener('click', () => {
    if (roundStatus !== 'waiting') {
        alert('Cannot add cards now. Wait for next round.');
        return;
    }
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

clearBtn.addEventListener('click', () => {
    if (roundStatus !== 'waiting') {
        alert('Cannot clear now. Wait for next round.');
        return;
    }
    selectedCards = [];
    renderSelectedCards();
});

confirmBtn.addEventListener('click', async () => {
    if (roundStatus !== 'waiting') {
        alert('Round already started. Wait for next round.');
        return;
    }
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
        balance = result.new_balance;
        selectedCards = [];
        renderSelectedCards();
        updateStats();
        fetchUserData();
        fetchMyCards(); // reload cards to show new ones
        Telegram.showPopup({ title: 'Success', message: 'Cards purchased!', buttons: [{type: 'ok'}] });
    } else {
        Telegram.showPopup({ title: 'Error', message: result.message, buttons: [{type: 'ok'}] });
    }
});

// Claim Bingo button
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
            fetchUserData();
            fetchMyCards();
        }
    });
});

// Initialize
buildGrid();
fetchUserData();
fetchMyCards();
setInterval(pollCalledNumbers, 2000);