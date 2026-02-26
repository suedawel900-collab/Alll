import json
import random
import os

def generate_bingo_cards(count=1000):
    """Generate unique bingo cards"""
    cards = []
    
    for card_id in range(1, count + 1):
        card = []
        
        # Column ranges: B:1-15, I:16-30, N:31-45, G:46-60, O:61-75
        ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
        
        for col in range(5):
            column = []
            min_num, max_num = ranges[col]
            
            # Generate 5 unique numbers for this column
            numbers = random.sample(range(min_num, max_num + 1), 5)
            column.extend(numbers)
            card.append(column)
        
        # FREE space in center (row 2, col 2)
        card[2][2] = "FREE"
        
        cards.append({
            "id": card_id,
            "card": card
        })
    
    # Save to file
    os.makedirs("static", exist_ok=True)
    with open("static/bingo_cards.json", "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2)
    
    print(f"✅ Generated {len(cards)} bingo cards")
    return cards

if __name__ == "__main__":
    generate_bingo_cards(1000)