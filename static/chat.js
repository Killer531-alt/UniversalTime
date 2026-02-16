// Global state
let gameState = {
    connected: false,
    universeId: null,
    characterId: null,
    studentName: null,
    classNumber: 1,
    currentCharacter: null,
    showTranslation: false,
};

// DOM Elements
const universeSelect = document.getElementById('universeSelect');
const characterSelect = document.getElementById('characterSelect');
const studentName = document.getElementById('studentName');
const classNumber = document.getElementById('classNumber');
const connectBtn = document.getElementById('connectBtn');
const evaluateBtn = document.getElementById('evaluateBtn');
const actionForm = document.getElementById('actionForm');
const actionInput = document.getElementById('actionInput');
const messagesBox = document.getElementById('messagesBox');
const connectionWarning = document.getElementById('connectionWarning');
const characterStats = document.getElementById('characterStats');
const loadingSpinner = document.getElementById('loadingSpinner');
const headerStatus = document.getElementById('headerStatus');


// Cargar universos en el select
async function loadUniverses() {
    try {
        const response = await fetch('/api/universes');
        const data = await response.json();
        const universes = data.universes || [];
        universeSelect.innerHTML = '<option value="">Selecciona un universo...</option>';
        universes.forEach(u => {
            const option = document.createElement('option');
            option.value = u.id;
            option.textContent = `${u.emoji || '🌌'} ${u.name}`;
            universeSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading universes:', error);
        universeSelect.innerHTML = '<option value="">Error cargando universos</option>';
    }
}

// Cargar personajes en el select
async function loadCharacters() {
    try {
        const response = await fetch('/api/characters');
        const data = await response.json();
        const characters = data.characters || [];
        characterSelect.innerHTML = '<option value="">Selecciona tu personaje...</option>';
        characters.forEach(c => {
            const option = document.createElement('option');
            option.value = c.id;
            option.textContent = `${c.emoji || '👤'} ${c.name} (${c.role || 'Aventurero'})`;
            characterSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading characters:', error);
        characterSelect.innerHTML = '<option value="">Error cargando personajes</option>';
    }
}

// Ejecutar carga al iniciar
document.addEventListener('DOMContentLoaded', async () => {
    await loadUniverses();
    await loadCharacters();
    connectBtn.addEventListener('click', connectGame);
    evaluateBtn.addEventListener('click', showGrade);
});


// Connect to game
async function connectGame() {
    const universe = universeSelect.value;
    const character = characterSelect.value;
    const name = studentName.value.trim();
    
    if (!universe || !character || !name) {
        alert('Por favor completa: universo, personaje y nombre');
        return;
    }
    
    gameState.universeId = universe;
    gameState.characterId = character;
    gameState.studentName = name;
    gameState.classNumber = parseInt(classNumber.value) || 1;
    gameState.connected = true;
    
    // Fetch character data
    try {
        const response = await fetch(`/api/character/${character}`);
        gameState.currentCharacter = await response.json();
    } catch (error) {
        console.error('Error loading character:', error);
    }
    
    // Update UI
    updateUI();
    // Render inventory now that we have currentCharacter
    try { renderInventory(); document.getElementById('inventoryPanel').style.display = 'block'; } catch (e) { }
    
    // Add system message
    addMessage(
        `¡Bienvenido, ${name}! Acabas de entrar al universo "${universeSelect.options[universeSelect.selectedIndex].text}". ¿Qué haces?`,
        'system'
    );
}

// Update UI based on connection state
function updateUI() {
    if (gameState.connected) {
        connectionWarning.style.display = 'none';
        actionForm.style.display = 'block';
        characterStats.style.display = 'block';
        evaluateBtn.style.display = 'block';
        
        // Disable selection inputs
        universeSelect.disabled = true;
        characterSelect.disabled = true;
        studentName.disabled = true;
        classNumber.disabled = true;
        connectBtn.textContent = '✓ Conectado';
        connectBtn.disabled = true;
        
        // Update header
        headerStatus.textContent = `Jugando como ${gameState.studentName} en Clase #${gameState.classNumber}`;
        
        // Update stats
        updateStats();
    }
}

// Update character stats display
function updateStats() {
    if (!gameState.currentCharacter) return;
    
    const char = gameState.currentCharacter;
    const lifePercent = (char.lifePercent || 1) * 100;
    
    document.getElementById('lifePercent').textContent = `${Math.round(lifePercent)}%`;
    document.getElementById('lifeBar').style.width = `${lifePercent}%`;
    
    // Update life bar color
    if (lifePercent > 50) {
        document.getElementById('lifeBar').style.background = '#4CAF50';
    } else if (lifePercent > 25) {
        document.getElementById('lifeBar').style.background = '#FF9800';
    } else {
        document.getElementById('lifeBar').style.background = '#f44336';
    }
    
    document.getElementById('pointsValue').textContent = char.points || 0;
    document.getElementById('moneyValue').textContent = char.money || 0;
    document.getElementById('currentUniverse').textContent = char.currentUniverse || gameState.universeId;
}

// Send action to game
async function sendAction(event) {
    event.preventDefault();
    
    if (!gameState.connected) {
        alert('Conéctate primero');
        return;
    }
    
    const prompt = actionInput.value.trim();
    if (!prompt) return;
    
    // Show user message
    addMessage(prompt, 'user');
    actionInput.value = '';
    
    // Show loading
    loadingSpinner.style.display = 'block';
    
    try {
        // Nuevo endpoint híbrido con Groq
        const response = await fetch('/ai/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playerId: gameState.characterId || gameState.studentName || 'player',
                message: prompt
            }),
        });
        const data = await response.json();
        if (response.ok) {
            // El nuevo endpoint retorna: { reply, effects, choices, source, tokensUsed, eventId }
            const narrative = data.reply || 'Sin respuesta';
            const effects = data.effects || {};
            const imageUrl = null;
            const choices = data.choices || [];
            const eventId = data.eventId || null;
            const imageNote = (typeof data.imageNote !== 'undefined') ? data.imageNote : null;
            showAIResponse(narrative, effects, imageUrl, imageNote, choices, eventId);
        } else {
            addMessage(`❌ Error: ${data.error || 'Error desconocido'}`, 'system');
        }
    } catch (error) {
        console.error('Error sending action:', error);
        addMessage(`❌ Error de conexión: ${error.message}`, 'system');
    } finally {
        loadingSpinner.style.display = 'none';
    }
}

// Show AI response with narrative, effects, choices and image
function showAIResponse(narrative, effects, imageUrl=null, imageNote=null, choices=[], eventId=null) {
    const content = document.createElement('div');
    
    // Add narrative with emoji
        // Mostrar solo la narrativa limpia si viene en formato JSON
        let cleanNarrative = narrative;
        try {
            if (typeof narrative === 'string' && narrative.trim().startsWith('{')) {
                const parsed = JSON.parse(narrative);
                if (parsed.narrative) cleanNarrative = parsed.narrative;
            }
        } catch (e) {}
        const narrativeEl = document.createElement('div');
        narrativeEl.className = 'narrative';
        narrativeEl.innerHTML = `📖 ${cleanNarrative}`;
        content.appendChild(narrativeEl);
    // If there is an image URL, render image first
    if (imageUrl) {
        try {
            const img = document.createElement('img');
            img.src = imageUrl;
            img.alt = 'Generated image';
            img.style.maxWidth = '320px';
            img.style.borderRadius = '8px';
            img.style.margin = '0.6rem 0';
            content.appendChild(img);
        } catch (e) {
            // ignore image errors
        }
    }
    // If there's an image note (generation attempted but unavailable), show it
    if (!imageUrl && imageNote) {
        const note = document.createElement('div');
        note.className = 'image-note';
        note.style.marginTop = '0.6rem';
        note.style.fontSize = '0.85rem';
        note.style.color = '#888';
        note.textContent = `🖼️ ${imageNote}`;
        content.appendChild(note);
    }

    // Add translation button
    const translateBtn = document.createElement('button');
    translateBtn.className = 'btn btn-translate';
    translateBtn.textContent = '🌐 Traducir al Español';
    translateBtn.style.marginTop = '0.5rem';
    translateBtn.style.fontSize = '0.85rem';
    translateBtn.style.padding = '0.4rem 0.8rem';
    translateBtn.style.width = 'auto';
    
    let translatedShown = false;
    const translatedSpan = document.createElement('div');
    translatedSpan.className = 'narrative translated';
    translatedSpan.style.display = 'none';
    translatedSpan.style.marginTop = '0.8rem';
    translatedSpan.style.color = '#d4a574';
    translatedSpan.style.fontStyle = 'italic';
    translatedSpan.style.borderLeft = '3px solid #f0ad4e';
    translatedSpan.style.paddingLeft = '0.8rem';
    
    translateBtn.onclick = async (e) => {
        e.preventDefault();
        
        if (translatedShown) {
            translatedSpan.style.display = translatedSpan.style.display === 'none' ? 'block' : 'none';
            return;
        }
        
        translateBtn.disabled = true;
        translateBtn.textContent = '⏳ Traduciendo...';
        
        try {
            const resp = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: narrative, target_lang: 'Spanish' }),
            });
            const data = await resp.json();
            
            translatedSpan.innerHTML = `📝 <strong>En Español:</strong> ${data.translated}`;
            translatedSpan.style.display = 'block';
            translateBtn.textContent = '✓ Ocultar traducción';
            translatedShown = true;
        } catch (error) {
            translateBtn.textContent = '❌ Error en traducción';
        } finally {
            translateBtn.disabled = false;
        }
    };
    
    content.appendChild(translateBtn);
    content.appendChild(translatedSpan);
    // Add effects if any
    if (Object.keys(effects).length > 0) {
        const effectsEl = document.createElement('div');
        effectsEl.className = 'effects';
        
        const title = document.createElement('div');
        title.className = 'effects-title';
        title.textContent = '⚡ Efectos de tu acción:';
        effectsEl.appendChild(title);
        
        Object.entries(effects).forEach(([key, value]) => {
            const item = document.createElement('div');
            item.className = 'effect-item';
            
            // Format effect display
            let displayKey = key;
            let displayValue = value;
            let emoji = '•';
            
            if (key === 'points') {
                displayKey = 'Puntos';
                emoji = value > 0 ? '⭐' : '❌';
                item.classList.add(value > 0 ? 'positive' : 'negative');
            } else if (key === 'money') {
                displayKey = 'Dinero';
                emoji = value > 0 ? '💰' : '💸';
                item.classList.add(value > 0 ? 'positive' : 'negative');
            } else if (key === 'lifePercent') {
                    displayKey = 'Vida';
                    // Siempre mostrar como delta en porcentaje
                    let dv = value;
                    try { dv = parseFloat(value); } catch (e) { dv = 0; }
                    let displayPct = 0;
                    if (Math.abs(dv) > 1) {
                        displayPct = Math.round(dv);
                    } else {
                        displayPct = Math.round(dv * 100);
                    }
                    displayValue = `${displayPct > 0 ? '+' : ''}${displayPct}%`;
                    emoji = displayPct > 0 ? '❤️' : '💔';
            } else if (key === 'skill') {
                displayKey = 'Habilidad';
                emoji = '🎯';
            } else if (key === 'gold') {
                displayKey = 'Oro';
                emoji = '🏆';
                item.classList.add(value > 0 ? 'positive' : 'negative');
            } else if (key === 'health') {
                displayKey = 'Salud';
                emoji = '💊';
                item.classList.add(value > 0 ? 'positive' : 'negative');
            } else if (key === 'skill_level') {
                displayKey = 'Nivel Habilidad';
                emoji = '📈';
            }
            
            item.innerHTML = `${emoji} <strong>${displayKey}:</strong> ${typeof displayValue === 'object' ? JSON.stringify(displayValue) : displayValue}`;
            effectsEl.appendChild(item);
        });
        
        content.appendChild(effectsEl);
    }

    // Render choices as buttons if present
    if (Array.isArray(choices) && choices.length > 0) {
        const choicesWrap = document.createElement('div');
        choicesWrap.className = 'choices-wrap';
        choicesWrap.style.marginTop = '0.6rem';
        const chTitle = document.createElement('div');
        chTitle.textContent = '🔀 Opciones:';
        chTitle.style.marginBottom = '0.4rem';
        choicesWrap.appendChild(chTitle);
        choices.forEach((ch, idx) => {
            const b = document.createElement('button');
            b.className = 'btn btn-choice';
            const text = (typeof ch === 'string') ? ch : (ch.description || ch.title || 'Opción');
            b.textContent = text;
            b.style.marginRight = '0.4rem';
            b.onclick = async () => {
                Array.from(choicesWrap.querySelectorAll('button')).forEach(x => x.disabled = true);
                // Enviar el texto de la opción seleccionada, character_id y universe_id
                await applyChoice({
                    choice_text: text,
                    character_id: gameState.characterId || gameState.currentCharacter?.id,
                    universe_id: gameState.universeId,
                    student: gameState.studentName,
                    class_number: gameState.classNumber
                });
            };
            choicesWrap.appendChild(b);
        });
        content.appendChild(choicesWrap);
    }
    
    addMessageElement(content, 'ai');
}

// Update character stats from effects
function updateCharacterFromEffects(effects) {
    if (!gameState.currentCharacter) return;
    
    const char = gameState.currentCharacter;
    
    if (effects.points) char.points = (char.points || 0) + effects.points;
    if (effects.money) char.money = (char.money || 0) + effects.money;
    if (effects.lifePercent !== undefined) {
        // Interpret lifePercent as a DELTA (percentage points) by default.
        // Accept either small fractions (0.05 => 5%) or integer percentage points (5 => 5%).
        let cur = parseFloat(char.lifePercent || 1.0);
        if (isNaN(cur)) cur = 1.0;
        let lp = effects.lifePercent;
        let delta = 0;
        try {
            lp = parseFloat(lp);
            if (Math.abs(lp) <= 1) {
                // fractional delta: 0.05 means +5 percentage points
                delta = lp;
            } else {
                // whole number treated as percentage points
                delta = lp / 100.0;
            }
        } catch (e) {
            delta = 0;
        }
        const newFrac = Math.max(0, Math.min(1, cur + delta));
        char.lifePercent = newFrac;
    }
    
    updateStats();
}

// Add message to chat
function addMessage(text, type) {
    const msgEl = document.createElement('div');
    msgEl.className = `message ${type}`;
    
    const content = document.createElement('div');
    content.className = 'content';
    content.textContent = text;
    
    msgEl.appendChild(content);
    messagesBox.appendChild(msgEl);
    
    // Auto-scroll to bottom
    messagesBox.scrollTop = messagesBox.scrollHeight;
}

// Add message element (for complex HTML content)
function addMessageElement(element, type) {
    const msgEl = document.createElement('div');
    msgEl.className = `message ${type}`;
    
    const content = document.createElement('div');
    content.className = 'content';
    content.appendChild(element);
    
    msgEl.appendChild(content);
    messagesBox.appendChild(msgEl);
    
    // Auto-scroll to bottom
    messagesBox.scrollTop = messagesBox.scrollHeight;
}

// Show grade
async function showGrade() {
    if (!gameState.characterId) {
        alert('Selecciona un personaje primero');
        return;
    }
    
    try {
        const response = await fetch(`/api/evaluate/${gameState.characterId}`);
        const data = await response.json();
        
        if (response.ok) {
            const grade = Math.round(data.grade * 100) / 100;
            document.getElementById('gradeValue').textContent = grade;
            document.getElementById('gradeInfo').style.display = 'block';
            
            addMessage(
                `📈 Tu calificación final es: ${grade}/100\n\n` +
                `Felicidades ${data.student}, completaste el desafío multiversal.`,
                'system'
            );
        } else {
            addMessage(`❌ Error: ${data.error}`, 'system');
        }
    } catch (error) {
        console.error('Error getting grade:', error);
        addMessage(`❌ Error obteniendo calificación: ${error.message}`, 'system');
    }
}

// Prevent form submission with Enter if not connected
document.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !gameState.connected) {
        e.preventDefault();
    }
});

// Market UI wiring
document.addEventListener('DOMContentLoaded', () => {
    const openBtn = document.getElementById('openMarketBtn');
    const closeBtn = document.getElementById('closeMarketBtn');
    const openInvBtn = document.getElementById('openInventoryBtn');
    const closeInvBtn = document.getElementById('closeInventoryBtn');
    const openMissionsBtn = document.getElementById('openMissionsBtn');
    const closeMissionsBtn = document.getElementById('closeMissionsBtn');
    const marketPanel = document.getElementById('marketPanel');
    const invPanel = document.getElementById('inventoryPanel');
    const missionsPanel = document.getElementById('missionsPanel');
    
    if (openBtn) openBtn.addEventListener('click', async () => {
        marketPanel.style.display = 'block';
        await loadMarketItems();
    });
    if (closeBtn) closeBtn.addEventListener('click', () => { marketPanel.style.display = 'none'; });
    if (openInvBtn) openInvBtn.addEventListener('click', () => {
        invPanel.style.display = 'block';
        renderInventory();
    });
    if (closeInvBtn) closeInvBtn.addEventListener('click', () => { invPanel.style.display = 'none'; });
    if (openMissionsBtn) openMissionsBtn.addEventListener('click', async () => {
        missionsPanel.style.display = 'block';
        await loadMissions();
    });
    if (closeMissionsBtn) closeMissionsBtn.addEventListener('click', () => { missionsPanel.style.display = 'none'; });
});

async function loadMarketItems() {
    const container = document.getElementById('marketItems');
    container.innerHTML = 'Cargando items...';
    try {
        const resp = await fetch('/api/market');
        const data = await resp.json();
        const items = data.items || [];
        if (!items.length) {
            container.innerHTML = '<em>No hay items en la tienda.</em>';
            return;
        }
        container.innerHTML = '';
        items.forEach(it => {
            const el = document.createElement('div');
            el.className = 'market-item';
            el.innerHTML = `<strong>${it.name}</strong> — ${it.description || ''} <br> Precio: ${it.price}`;
            const buyBtn = document.createElement('button');
            buyBtn.className = 'btn btn-primary';
            buyBtn.textContent = 'Comprar';
            buyBtn.onclick = async () => {
                await buyMarketItem(it.id);
            };
            el.appendChild(buyBtn);
            container.appendChild(el);
        });
    } catch (e) {
        container.innerHTML = '<em>Error cargando la tienda.</em>';
    }
}

async function buyMarketItem(itemId) {
    if (!gameState.characterId) { alert('Selecciona un personaje primero'); return; }
    try {
        const resp = await fetch('/api/market/buy', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ character_id: gameState.characterId, item_id: itemId })
        });
        const data = await resp.json();
        if (resp.ok) {
            // update local character and UI
            if (data.character) {
                gameState.currentCharacter = data.character;
                updateStats();
                try { renderInventory(); } catch (e) {}
            }
            addMessage(`🛒 Compraste: ${data.item.name}`, 'system');
            await loadMarketItems();
        } else {
            addMessage(`❌ No se pudo comprar: ${data.error || 'error'}`, 'system');
        }
    } catch (e) {
        addMessage(`❌ Error en compra: ${e.message}`, 'system');
    }
}

// Apply a choice by calling /api/choice and rendering result
async function applyChoice(payload) {
    try {
        // Mostrar la opción elegida como mensaje del usuario
        addMessage(payload.choice_text, 'user');
        // Llamar al backend para procesar la opción como mensaje nuevo
        const resp = await fetch('/api/choice', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        let data = null;
        try {
            data = await resp.json();
        } catch (e) {
            addMessage('❌ Error: respuesta inválida del servidor.', 'system');
            return;
        }
        if (resp.ok && data) {
            const ev = data.event || {};
            const result = data.applied || {};
            const narrative = data.narrative || (ev.result && ev.result.narrative) || (result.narrative) || 'Acción registrada.';
            const effects = data.effects || (ev.result && ev.result.effects) || (result.effects) || {};
            // Actualizar el personaje si viene actualizado
            let personajeActualizado = data.character || result.character || ev.character || null;
            if (personajeActualizado) {
                gameState.currentCharacter = personajeActualizado;
                updateStats();
            } else if (gameState.characterId) {
                // Si no viene personaje actualizado, forzar recarga desde backend
                try {
                    const r = await fetch(`/api/character/${gameState.characterId}`);
                    const d = await r.json();
                    if (d && d.id) { gameState.currentCharacter = d; updateStats(); }
                } catch {}
            }
            // 20% de probabilidad de generar nuevas opciones
            let newChoices = [];
            if (Math.random() < 0.2) {
                if (Array.isArray(data.choices) && data.choices.length > 0) {
                    newChoices = data.choices;
                } else {
                    newChoices = [
                        'Explorar una ruta alternativa',
                        'Buscar pistas adicionales',
                        'Descansar y observar el entorno'
                    ];
                }
            } else {
                newChoices = Array.isArray(data.choices) ? data.choices : [];
            }
            showAIResponse(narrative, effects, ev.image || null, ev.image_note || null, newChoices, ev.id || ev.event_id);
        } else {
            addMessage(`❌ Error aplicando opción: ${data && data.error ? data.error : 'error'}`, 'system');
            // Siempre intentar actualizar stats aunque haya error
            if (gameState.characterId) {
                try {
                    const r = await fetch(`/api/character/${gameState.characterId}`);
                    const d = await r.json();
                    if (d && d.id) { gameState.currentCharacter = d; updateStats(); }
                } catch {}
            }
        }
    } catch (e) {
        addMessage(`❌ Error al aplicar opción: ${e.message}`, 'system');
        // Siempre intentar actualizar stats aunque haya error
        if (gameState.characterId) {
            try {
                const r = await fetch(`/api/character/${gameState.characterId}`);
                const d = await r.json();
                if (d && d.id) { gameState.currentCharacter = d; updateStats(); }
            } catch {}
        }
    }
}

// Inventory UI: show inventory for connected character
async function loadInventoryUI() {
    const panel = document.getElementById('marketPanel');
    // reuse marketPanel for inventory listing below market items
    const container = document.createElement('div');
    container.id = 'inventoryPanel';
    container.style.marginTop = '1rem';
    panel.appendChild(container);
    renderInventory();
}

async function renderInventory() {
    const container = document.getElementById('inventoryItems');
    if (!container) return;
    container.innerHTML = '';
    if (!gameState.currentCharacter) {
        container.innerHTML += '<div><em>No conectado</em></div>';
        return;
    }
    const inv = gameState.currentCharacter.inventory || [];
    if (!inv.length) {
        container.innerHTML += '<div><em>Inventario vacío</em></div>';
        return;
    }
    inv.forEach(item => {
        const el = document.createElement('div');
        el.className = 'inv-item';
        el.innerHTML = `<strong>${item.name}</strong> — ${item.description || ''}`;
        const useBtn = document.createElement('button');
        useBtn.className = 'btn btn-primary';
        useBtn.textContent = 'Usar';
        useBtn.onclick = async () => {
            useBtn.disabled = true;
            try {
                const resp = await fetch('/api/inventory/use', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ character_id: gameState.characterId, item_id: item.id, student: gameState.studentName, class_number: gameState.classNumber }) });
                const data = await resp.json();
                if (resp.ok) {
                    addMessage(`🎯 Usaste: ${item.name}`,'system');
                    if (data.character) { gameState.currentCharacter = data.character; updateStats(); }
                    // show resulting narrative/effects
                    const ev = data.event || {};
                    const applied = data.applied || {};
                    const narrative = (ev.result && ev.result.narrative) || applied.narrative || 'Item usado.';
                    const effects = (ev.result && ev.result.effects) || applied.effects || {};
                    showAIResponse(narrative, effects, ev.image || null, ev.image_note || null, ev.choices || [], ev.id || ev.event_id);
                } else {
                    addMessage(`❌ No se pudo usar: ${data.error || 'error'}`,'system');
                }
            } catch (e) {
                addMessage(`❌ Error usando item: ${e.message}`,'system');
            } finally {
                useBtn.disabled = false;
                renderInventory();
            }
        };
        el.appendChild(useBtn);
        container.appendChild(el);
    });
}

// Missions functions
async function loadMissions() {
    const container = document.getElementById('missionsList');
    container.innerHTML = 'Cargando misiones...';
    try {
        const resp = await fetch('/api/missions');
        const data = await resp.json();
        const missions = data.missions || [];
        if (!missions.length) {
            container.innerHTML = '<em>No hay misiones disponibles.</em>';
            return;
        }
        container.innerHTML = '';
        missions.forEach(m => {
            const el = document.createElement('div');
            el.style.marginBottom = '0.8rem';
            el.style.padding = '0.8rem';
            el.style.background = 'rgba(255,255,255,0.05)';
            el.style.borderRadius = '4px';
            el.style.borderLeft = '3px solid #667eea';
            el.innerHTML = `<strong>${m.title}</strong> <br/> <small>${m.description}</small> <br/> <span style="color:#4CAF50;">Recompensa: +${m.reward_points} pts, +${m.reward_money} monedas</span> <br/> <span style="color:#FFB74D; font-size:0.85rem;">Dificultad: ${m.difficulty}</span>`;
            const startBtn = document.createElement('button');
            startBtn.className = 'btn btn-primary';
            startBtn.textContent = 'Iniciar misión';
            startBtn.onclick = async () => {
                startBtn.disabled = true;
                await startMissionLLM(m);
                startBtn.disabled = false;
            };
            el.appendChild(startBtn);
            container.appendChild(el);
        });
    } catch (e) {
        container.innerHTML = '<em>Error cargando misiones.</em>';
    }
}

// Nueva función: iniciar misión y conectar al LLM
async function startMissionLLM(mission) {
    const resultDiv = document.getElementById('missionStartResult');
    resultDiv.innerHTML = 'Generando narrativa...';
    try {
        const resp = await fetch('/api/mission/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                mission_id: mission.id,
                character_id: gameState.characterId,
                universe_id: gameState.universeId,
                student: gameState.studentName,
                class_number: gameState.classNumber
            })
        });
        const data = await resp.json();
        if (resp.ok && data.narrative) {
            resultDiv.innerHTML = `<div class="mission-narrative">${data.narrative}</div>`;
            addMessage(`🧭 Misión iniciada: ${mission.title}\n${data.narrative}`, 'system');
        } else {
            resultDiv.innerHTML = `<em>Error: ${data.error || 'No se pudo iniciar la misión.'}</em>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<em>Error: ${e.message}</em>`;
    }
}
  