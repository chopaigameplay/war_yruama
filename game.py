import sqlite3
import random
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dataclasses import dataclass

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Substitua por uma chave secreta segura

# Configuração do banco de dados
conn = sqlite3.connect('game.db', check_same_thread=False)
cursor = conn.cursor()

# Criar tabelas
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        clan TEXT NOT NULL,
        pos_x INTEGER NOT NULL,
        pos_y INTEGER NOT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS cities (
        user_id INTEGER PRIMARY KEY,
        wood INTEGER DEFAULT 100,
        stone INTEGER DEFAULT 100,
        silver INTEGER DEFAULT 100,
        food INTEGER DEFAULT 100,
        last_resource_update INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS buildings (
        user_id INTEGER,
        building TEXT,
        level INTEGER DEFAULT 1,
        upgrade_time INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, building),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS units (
        user_id INTEGER,
        unit_type TEXT,
        quantity INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, unit_type),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS attacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attacker_id INTEGER,
        defender_id INTEGER,
        units INTEGER,
        start_time INTEGER,
        duration INTEGER,
        return_time INTEGER,
        status TEXT,
        result TEXT,
        FOREIGN KEY (attacker_id) REFERENCES users(id),
        FOREIGN KEY (defender_id) REFERENCES users(id)
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS exploration_zones (
        zone_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        loot_wood INTEGER,
        loot_stone INTEGER,
        loot_silver INTEGER,
        loot_food INTEGER,
        pos_x INTEGER,
        pos_y INTEGER,
        last_explored INTEGER,
        cooldown INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
''')
conn.commit()

# Definições de dados
UPGRADE_COSTS = {
    "sawmill": {1: {"wood": 20, "stone": 10, "silver": 0}, 2: {"wood": 50, "stone": 30, "silver": 10}},
    "quarry": {1: {"wood": 10, "stone": 20, "silver": 0}, 2: {"wood": 30, "stone": 50, "silver": 10}},
    "silver_mine": {1: {"wood": 10, "stone": 10, "silver": 20}, 2: {"wood": 30, "stone": 30, "silver": 50}},
    "farm": {1: {"wood": 10, "stone": 10, "silver": 0}, 2: {"wood": 30, "stone": 30, "silver": 10}},
    "barracks": {1: {"wood": 20, "stone": 20, "silver": 10}, 2: {"wood": 50, "stone": 50, "silver": 30}},
    "wall": {1: {"wood": 30, "stone": 30, "silver": 10}, 2: {"wood": 70, "stone": 70, "silver": 30}},
    "port": {1: {"wood": 20, "stone": 20, "silver": 20}, 2: {"wood": 50, "stone": 50, "silver": 50}},
    "house": {1: {"wood": 10, "stone": 10, "silver": 5}, 2: {"wood": 30, "stone": 30, "silver": 15}}
}

UNITS = {
    "soldier": {"attack": 10, "defense": 5, "movement": 2, "food_cost": 1, "house_cost": 1, "barracks_level": 1},
    "archer": {"attack": 15, "defense": 3, "movement": 1, "food_cost": 2, "house_cost": 1, "barracks_level": 2},
    "cavalry": {"attack": 20, "defense": 10, "movement": 3, "food_cost": 3, "house_cost": 2, "barracks_level": 3}
}

# Taxas de geração de recursos por nível (unidades por segundo)
RESOURCE_RATES = {
    "sawmill": {1: 0.1, 2: 0.3},  # Madeira por segundo
    "quarry": {1: 0.1, 2: 0.3},   # Pedra por segundo
    "silver_mine": {1: 0.05, 2: 0.15},  # Prata por segundo
    "farm": {1: 0.2, 2: 0.5}      # Alimento por segundo
}

# Limites máximos de armazenamento por nível
STORAGE_LIMITS = {
    "sawmill": {1: 500, 2: 1000},  # Limite máximo de madeira
    "quarry": {1: 500, 2: 1000},   # Limite máximo de pedra
    "silver_mine": {1: 300, 2: 600},  # Limite máximo de prata
    "farm": {1: 800, 2: 1500}      # Limite máximo de alimento
}

# Lista de posições fixas para cidades dos jogadores (em porcentagem)
FIXED_CITY_POSITIONS = [
    (20, 20),  # Posição 1
    (30, 70),  # Posição 2
    (50, 40),  # Posição 3
    (70, 30),  # Posição 4
    (80, 80),  # Posição 5
    # Adicione mais posições conforme necessário
]

@dataclass
class Building:
    name: str
    level: int
    cost: dict
    upgrade_time: int

@dataclass
class Unit:
    type: str
    quantity: int
    attack: int
    defense: int
    movement: int
    food_cost: int
    house_cost: int
    barracks_level: int

def get_username(user_id):
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    return cursor.fetchone()[0]

def assign_city_position():
    cursor.execute('SELECT COUNT(*) FROM users')
    user_count = cursor.fetchone()[0]
    if user_count < len(FIXED_CITY_POSITIONS):
        return FIXED_CITY_POSITIONS[user_count]
    else:
        # Caso todas as posições fixas estejam ocupadas, você pode decidir o que fazer
        # Aqui, estou retornando a última posição como fallback
        return FIXED_CITY_POSITIONS[-1]

def update_resources(user_id):
    current_time = int(time.time())
    cursor.execute('SELECT wood, stone, silver, food, last_resource_update FROM cities WHERE user_id = ?', (user_id,))
    resources = cursor.fetchone()
    if not resources:
        return
    wood, stone, silver, food, last_update = resources
    
    if last_update == 0:
        cursor.execute('UPDATE cities SET last_resource_update = ? WHERE user_id = ?', (current_time, user_id))
        conn.commit()
        return
    
    time_elapsed = current_time - last_update
    cursor.execute('SELECT building, level FROM buildings WHERE user_id = ?', (user_id,))
    building_levels = cursor.fetchall()
    
    # Calcular limites máximos com base no nível das construções
    max_wood = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "sawmill")
    max_stone = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "quarry")
    max_silver = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "silver_mine")
    max_food = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "farm")
    
    # Calcular taxas de geração
    wood_rate = sum(RESOURCE_RATES.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "sawmill")
    stone_rate = sum(RESOURCE_RATES.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "quarry")
    silver_rate = sum(RESOURCE_RATES.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "silver_mine")
    food_rate = sum(RESOURCE_RATES.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "farm")
    
    # Calcular novos valores respeitando os limites
    new_wood = min(wood + int(wood_rate * time_elapsed), max_wood)
    new_stone = min(stone + int(stone_rate * time_elapsed), max_stone)
    new_silver = min(silver + int(silver_rate * time_elapsed), max_silver)
    new_food = min(food + int(food_rate * time_elapsed), max_food)
    
    cursor.execute('''
        UPDATE cities SET wood = ?, stone = ?, silver = ?, food = ?, last_resource_update = ?
        WHERE user_id = ?
    ''', (new_wood, new_stone, new_silver, new_food, current_time, user_id))
    conn.commit()
    
    return {
        'wood': new_wood,
        'stone': new_stone,
        'silver': new_silver,
        'food': new_food,
        'max_wood': max_wood,
        'max_stone': max_stone,
        'max_silver': max_silver,
        'max_food': max_food
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    cursor.execute('SELECT id, password FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    if user and user[1] == password:
        session['user_id'] = user[0]
        return redirect(url_for('game'))
    return "Usuário ou senha inválidos", 401

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    clan = request.form['clan']
    
    if password != confirm_password:
        return "As senhas não coincidem", 400
    
    try:
        # Atribuir posição fixa ao novo jogador
        pos_x, pos_y = assign_city_position()
        cursor.execute('INSERT INTO users (username, email, password, clan, pos_x, pos_y) VALUES (?, ?, ?, ?, ?, ?)', 
                       (username, email, password, clan, pos_x, pos_y))
        user_id = cursor.lastrowid
        # Inicializar cidade com recursos padrão
        cursor.execute('INSERT INTO cities (user_id, wood, stone, silver, food) VALUES (?, 100, 100, 100, 100)', (user_id,))
        for building in UPGRADE_COSTS.keys():
            cursor.execute('INSERT INTO buildings (user_id, building) VALUES (?, ?)', (user_id, building))
        conn.commit()
        session['user_id'] = user_id
        return redirect(url_for('game'))
    except sqlite3.IntegrityError:
        return "Este e-mail já está em uso. Por favor, use um e-mail diferente.", 400

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        if user:
            # Simulação de envio de email (implementar lógica real se necessário)
            return redirect(url_for('reset_password'))
        return "Email não encontrado", 404
    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            return "As senhas não coincidem", 400
        # Simulação de atualização de senha (implementar lógica real se necessário)
        return redirect(url_for('index'))
    return render_template('reset_password.html')

@app.route('/game')
def game():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    username = get_username(user_id)
    current_time = int(time.time())
    
    # Obter posição do jogador atual
    cursor.execute('SELECT pos_x, pos_y FROM users WHERE id = ?', (user_id,))
    player_position = cursor.fetchone()
    if not player_position:
        return "Usuário não encontrado", 404
    player_pos_x, player_pos_y = player_position
    
    # Verificar e inicializar recursos se não existirem
    cursor.execute('SELECT wood, stone, silver, food, last_resource_update FROM cities WHERE user_id = ?', (user_id,))
    resources = cursor.fetchone()
    if not resources:
        cursor.execute('INSERT INTO cities (user_id, wood, stone, silver, food, last_resource_update) VALUES (?, 100, 100, 100, 100, ?)', (user_id, current_time))
        conn.commit()
        resource_data = {'wood': 100, 'stone': 100, 'silver': 100, 'food': 100, 'max_wood': 500, 'max_stone': 500, 'max_silver': 300, 'max_food': 800}
    else:
        wood, stone, silver, food, last_update = resources
        if last_update == 0:
            cursor.execute('UPDATE cities SET last_resource_update = ? WHERE user_id = ?', (current_time, user_id))
            conn.commit()
        resource_data = update_resources(user_id) or {'wood': wood, 'stone': stone, 'silver': silver, 'food': food, 'max_wood': 500, 'max_stone': 500, 'max_silver': 300, 'max_food': 800}
    
    wood = resource_data['wood']
    stone = resource_data['stone']
    silver = resource_data['silver']
    food = resource_data['food']
    max_wood = resource_data['max_wood']
    max_stone = resource_data['max_stone']
    max_silver = resource_data['max_silver']
    max_food = resource_data['max_food']
    
    # Construções
    buildings = []
    for building in UPGRADE_COSTS.keys():
        cursor.execute('SELECT level, upgrade_time FROM buildings WHERE user_id = ? AND building = ?', (user_id, building))
        result = cursor.fetchone()
        if result:
            level, upgrade_time = result
        else:
            level, upgrade_time = 1, 0
            cursor.execute('INSERT INTO buildings (user_id, building, level, upgrade_time) VALUES (?, ?, ?, ?)', (user_id, building, level, upgrade_time))
        cost = UPGRADE_COSTS[building][level]
        buildings.append(Building(building, level, cost, upgrade_time))
    conn.commit()
    
    # Unidades
    units = []
    for unit_type, stats in UNITS.items():
        cursor.execute('SELECT quantity FROM units WHERE user_id = ? AND unit_type = ?', (user_id, unit_type))
        result = cursor.fetchone()
        quantity = result[0] if result else 0
        units.append(Unit(unit_type, quantity, stats['attack'], stats['defense'], stats['movement'], stats['food_cost'], stats['house_cost'], stats['barracks_level']))
    
    # Outros jogadores com suas posições fixas
    cursor.execute('SELECT id, username, pos_x, pos_y FROM users WHERE id != ?', (user_id,))
    users = cursor.fetchall()
    
    # Ataques
    cursor.execute('SELECT * FROM attacks WHERE attacker_id = ? OR defender_id = ?', (user_id, user_id))
    attacks = cursor.fetchall()
    
    # Zonas de Exploração
    cursor.execute('SELECT * FROM exploration_zones WHERE user_id = ?', (user_id,))
    exploration_zones = cursor.fetchall()
    
    # Garantir que sempre haja 5 zonas de exploração disponíveis
    available_zones = []
    for zone in exploration_zones:
        zone_id, _, name, difficulty, loot_wood, loot_stone, loot_silver, loot_food, pos_x, pos_y, last_explored, cooldown = zone
        if last_explored is None or (current_time - last_explored >= cooldown):
            available_zones.append({
                'zone_id': zone_id,
                'name': name,
                'difficulty': difficulty,
                'loot': {'wood': loot_wood, 'stone': loot_stone, 'silver': loot_silver, 'food': loot_food},
                'pos_x': pos_x,
                'pos_y': pos_y,
                'can_explore': True
            })
    
    # Se houver menos de 5 zonas disponíveis, criar novas
    while len(available_zones) < 5:
        zone_id = len(exploration_zones) + len(available_zones) + 1
        name = f"Zona {zone_id}"
        difficulty = random.choice(['easy', 'medium', 'hard'])
        loot = {
            'wood': random.randint(50, 150) * (1 + ['easy', 'medium', 'hard'].index(difficulty)),
            'stone': random.randint(50, 150) * (1 + ['easy', 'medium', 'hard'].index(difficulty)),
            'silver': random.randint(50, 150) * (1 + ['easy', 'medium', 'hard'].index(difficulty)),
            'food': random.randint(50, 150) * (1 + ['easy', 'medium', 'hard'].index(difficulty))
        }
        pos_x = random.randint(10, 90)
        pos_y = random.randint(10, 90)
        cursor.execute('''
            INSERT INTO exploration_zones (user_id, name, difficulty, loot_wood, loot_stone, loot_silver, loot_food, pos_x, pos_y, last_explored, cooldown)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, difficulty, loot['wood'], loot['stone'], loot['silver'], loot['food'], pos_x, pos_y, None, 7200))  # 2 horas de cooldown
        conn.commit()
        available_zones.append({
            'zone_id': zone_id,
            'name': name,
            'difficulty': difficulty,
            'loot': loot,
            'pos_x': pos_x,
            'pos_y': pos_y,
            'can_explore': True
        })
    
    return render_template('game.html', username=username, wood=wood, stone=stone, silver=silver, food=food,
                           max_wood=max_wood, max_stone=max_stone, max_silver=max_silver, max_food=max_food,
                           buildings=buildings, upgrade_costs_keys=list(UPGRADE_COSTS.keys()), units=units,
                           users=users, attacks=attacks, current_time=current_time, exploration_zones=available_zones,
                           player_pos_x=player_pos_x, player_pos_y=player_pos_y, random=random)

@app.route('/upgrade', methods=['POST'])
def upgrade():
    if 'user_id' not in session:
        return jsonify({'message': 'Usuário não autenticado'}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    building = data.get('building')
    
    cursor.execute('SELECT level, upgrade_time FROM buildings WHERE user_id = ? AND building = ?', (user_id, building))
    result = cursor.fetchone()
    if not result:
        return jsonify({'message': 'Construção não encontrada'}), 404
    level, upgrade_time = result
    
    if upgrade_time > int(time.time()):
        return jsonify({'message': 'A construção já está sendo melhorada'}), 400
    
    cost = UPGRADE_COSTS[building][level]
    cursor.execute('SELECT wood, stone, silver FROM cities WHERE user_id = ?', (user_id,))
    resources = cursor.fetchone()
    if not resources or resources[0] < cost['wood'] or resources[1] < cost['stone'] or resources[2] < cost['silver']:
        return jsonify({'message': 'Recursos insuficientes'}), 400
    
    new_upgrade_time = int(time.time()) + 3600  # 1 hora de upgrade
    cursor.execute('UPDATE buildings SET upgrade_time = ? WHERE user_id = ? AND building = ?', (new_upgrade_time, user_id, building))
    cursor.execute('UPDATE cities SET wood = wood - ?, stone = stone - ?, silver = silver - ? WHERE user_id = ?', (cost['wood'], cost['stone'], cost['silver'], user_id))
    conn.commit()
    return jsonify({'message': f'{building.capitalize()} sendo melhorada'})

@app.route('/train_units', methods=['POST'])
def train_units():
    if 'user_id' not in session:
        return jsonify({'message': 'Usuário não autenticado'}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    unit_type = data.get('unit_type')
    quantity = int(data.get('quantity'))
    
    if unit_type not in UNITS:
        return jsonify({'message': 'Tipo de unidade inválido'}), 400
    
    unit = UNITS[unit_type]
    cursor.execute('SELECT level FROM buildings WHERE user_id = ? AND building = ?', (user_id, 'barracks'))
    barracks_level = cursor.fetchone()[0] if cursor.fetchone() else 1
    if unit['barracks_level'] > barracks_level:
        return jsonify({'message': 'Nível do quartel insuficiente'}), 400
    
    food_cost = unit['food_cost'] * quantity
    house_cost = unit['house_cost'] * quantity
    cursor.execute('SELECT food, wood FROM cities WHERE user_id = ?', (user_id,))
    resources = cursor.fetchone()
    if not resources or resources[0] < food_cost or resources[1] < house_cost:
        return jsonify({'message': 'Recursos insuficientes'}), 400
    
    cursor.execute('UPDATE cities SET food = food - ?, wood = wood - ? WHERE user_id = ?', (food_cost, house_cost, user_id))
    cursor.execute('INSERT OR REPLACE INTO units (user_id, unit_type, quantity) VALUES (?, ?, COALESCE((SELECT quantity FROM units WHERE user_id = ? AND unit_type = ?), 0) + ?)', (user_id, unit_type, user_id, unit_type, quantity))
    conn.commit()
    return jsonify({'message': f'{quantity} {unit_type}s treinados'})

@app.route('/attack', methods=['GET', 'POST'])
def attack():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    username = get_username(user_id)
    
    if request.method == 'POST':
        target_username = request.form['target_username']
        quantity = int(request.form['quantity'])
        
        cursor.execute('SELECT id FROM users WHERE username = ?', (target_username,))
        target_user = cursor.fetchone()
        if not target_user:
            return "Usuário alvo não encontrado", 404
        target_id = target_user[0]
        
        cursor.execute('SELECT quantity FROM units WHERE user_id = ? AND unit_type = ?', (user_id, 'soldier'))
        units = cursor.fetchone()[0] if cursor.fetchone() else 0
        if quantity > units:
            return "Unidades insuficientes", 400
        
        duration = random.randint(300, 600)  # 5-10 minutos
        start_time = int(time.time())
        return_time = start_time + duration
        cursor.execute('INSERT INTO attacks (attacker_id, defender_id, units, start_time, duration, return_time, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (user_id, target_id, quantity, start_time, duration, return_time, 'in_progress'))
        cursor.execute('UPDATE units SET quantity = quantity - ? WHERE user_id = ? AND unit_type = ?', (quantity, user_id, 'soldier'))
        conn.commit()
        return redirect(url_for('game'))
    
    target_username = request.args.get('target')
    if target_username:
        cursor.execute('SELECT id FROM users WHERE username = ?', (target_username,))
        target_user = cursor.fetchone()
        if target_user:
            target_id = target_user[0]
            duration = random.randint(300, 600)
            return_time = int(time.time()) + duration
            return render_template('attack.html', target_username=target_username, duration=duration, return_duration=duration)
    return redirect(url_for('game'))

@app.route('/explore', methods=['POST'])
def explore():
    if 'user_id' not in session:
        return jsonify({'message': 'Usuário não autenticado'}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    zone_id = data.get('zone_id')
    quantity = int(data.get('quantity'))
    
    if quantity <= 0:
        return jsonify({'message': 'Quantidade inválida'}), 400
    
    # Verificar se a zona existe e está disponível
    cursor.execute('SELECT * FROM exploration_zones WHERE user_id = ? AND zone_id = ?', (user_id, zone_id))
    zone = cursor.fetchone()
    if not zone:
        return jsonify({'message': 'Zona de exploração não encontrada'}), 404
    
    zone_id, _, name, difficulty, loot_wood, loot_stone, loot_silver, loot_food, pos_x, pos_y, last_explored, cooldown = zone
    current_time = int(time.time())
    
    if last_explored and (current_time - last_explored < cooldown):
        return jsonify({'message': f'Zona {name} está em cooldown. Tente novamente mais tarde.'}), 403
    
    # Calcular limites máximos para evitar exceder o armazenamento
    cursor.execute('SELECT building, level FROM buildings WHERE user_id = ?', (user_id,))
    building_levels = cursor.fetchall()
    max_wood = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "sawmill")
    max_stone = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "quarry")
    max_silver = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "silver_mine")
    max_food = sum(STORAGE_LIMITS.get(b[0], {1: 0})[b[1]] for b in building_levels if b[0] == "farm")
    
    cursor.execute('SELECT wood, stone, silver, food FROM cities WHERE user_id = ?', (user_id,))
    current_resources = cursor.fetchone()
    wood, stone, silver, food = current_resources
    
    # Verificar se há espaço para adicionar o loot
    if (wood + loot_wood > max_wood or stone + loot_stone > max_stone or
        silver + loot_silver > max_silver or food + loot_food > max_food):
        return jsonify({'message': 'Espaço de armazenamento insuficiente para o loot!'}), 400
    
    # Calcular distância do ponto azul (cidade do jogador) ao ponto amarelo
    cursor.execute('SELECT pos_x, pos_y FROM users WHERE id = ?', (user_id,))
    player_pos = cursor.fetchone()
    player_pos_x, player_pos_y = player_pos
    distance = ((pos_x - player_pos_x) ** 2 + (pos_y - player_pos_y) ** 2) ** 0.5
    travel_time = int(distance * 10)  # 10 segundos por unidade de distância
    
    # Verificar unidades disponíveis
    cursor.execute('SELECT quantity FROM units WHERE user_id = ? AND unit_type = ?', (user_id, 'soldier'))
    units = cursor.fetchone()[0] if cursor.fetchone() else 0
    if quantity > units:
        return jsonify({'message': 'Unidades insuficientes para explorar'}), 400
    
    # Simular exploração
    success_chance = {'easy': 0.9, 'medium': 0.7, 'hard': 0.5}[difficulty]
    success = random.random() < success_chance
    
    if success:
        # Adicionar loot aos recursos do jogador
        cursor.execute('UPDATE cities SET wood = wood + ?, stone = stone + ?, silver = silver + ?, food = food + ? WHERE user_id = ?',
                       (loot_wood, loot_stone, loot_silver, loot_food, user_id))
        # Atualizar timestamp de última exploração e mudar a posição da zona
        new_pos_x = random.randint(10, 90)
        new_pos_y = random.randint(10, 90)
        cursor.execute('UPDATE exploration_zones SET last_explored = ?, pos_x = ?, pos_y = ? WHERE zone_id = ?', 
                       (current_time + travel_time, new_pos_x, new_pos_y, zone_id))
        conn.commit()
        return jsonify({'message': f'Exploração bem-sucedida! Você ganhou: {loot_wood} Madeira, {loot_stone} Pedra, {loot_silver} Prata, {loot_food} Alimento.'})
    else:
        # Reduzir unidades (simulando perda na exploração)
        cursor.execute('UPDATE units SET quantity = quantity - ? WHERE user_id = ? AND unit_type = ?', (quantity // 2, user_id, 'soldier'))
        conn.commit()
        return jsonify({'message': 'Exploração falhou! Você perdeu algumas unidades.'})

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/game_resources')
def game_resources():
    if 'user_id' not in session:
        return jsonify({'error': 'Usuário não autenticado'}), 401
    
    user_id = session['user_id']
    resource_data = update_resources(user_id)
    if not resource_data:
        return jsonify({'error': 'Cidade não encontrada'}), 404
    
    return jsonify({
        'wood': resource_data['wood'],
        'stone': resource_data['stone'],
        'silver': resource_data['silver'],
        'food': resource_data['food'],
        'max_wood': resource_data['max_wood'],
        'max_stone': resource_data['max_stone'],
        'max_silver': resource_data['max_silver'],
        'max_food': resource_data['max_food']
    })

if __name__ == '__main__':
    app.run(debug=True)