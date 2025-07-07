import os
import json
import datetime
import psycopg2
from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

# ====================================
# ✅ VARIÁVEIS DE AMBIENTE FIXAS
# ====================================
TOKEN = os.environ.get("TOKEN","7333842067:AAEynLOdFTnJeMRw-fhYhfU-UT0PFXoTduE")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://enviamos-bot.onrender.com")

CHAVE_PIX = os.environ.get("CHAVE_PIX","pattywatanabe@outlook.com")
URL_WHATSAPP = os.environ.get("URL_WHATSAPP", "https://wa.me/818030734889")
URL_FORMULARIO = os.environ.get("URL_FORMULARIO","https://forms.gle/SBV9vUrenLN7VELi6")
VALOR_IENE_REAL = float(os.environ.get("VALOR_IENE_REAL", 0.039))
TAXA_SERVICO = float(os.environ.get("TAXA_SERVICO", 0.20))
BOT_USERNAME = os.environ.get("BOT_USERNAME","@Enviamosjpbot")
GROUP_USERNAME = os.environ.get("GROUP_USERNAME","@enviamos_jp") 
ADMIN_IDS = [7968066840]

# ====================================
# ✅ BANCO DE DADOS POSTGRESQL
# ====================================
DB_NAME = os.environ.get("DB_NAME", "enviamosjp_db")
DB_USER = os.environ.get("DB_USER", "enviamosjp_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "KH2ry19WxnF60qRQtRSVjdYYt8g9blCG")
DB_HOST = os.environ.get("DB_HOST", "dpg-d1lmd96r433s73dta9p0-a")

def conectar_db():
    return psycopg2.connect(
        dbname=DB_NAME, user=DB_USER,
        password=DB_PASSWORD, host=DB_HOST
    )

# ====================================
# ✅ ESTRUTURAS EM MEMÓRIA
# ====================================
cadastro_temp = {}
imagens_pedido = {}

NOME, DESCRICAO, PRECO, FOTO = range(4)

# ====================================
# ✅ FUNÇÕES UTILITÁRIAS
# ====================================
def salvar_produto_pg(produto):
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO produtos (nome, descricao, preco, foto) VALUES (%s, %s, %s, %s);",
        (produto["nome"], produto["descricao"], produto["preco"], produto["foto"])
    )
    conn.commit()
    cur.close()
    conn.close()

def obter_produtos_pg():
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("SELECT id, nome, descricao, preco, foto FROM produtos;")
    rows = cur.fetchall()
    produtos = {}
    for row in rows:
        produtos[str(row[0])] = {
            "nome": row[1],
            "descricao": row[2],
            "preco": row[3],
            "foto": row[4]
        }
    cur.close()
    conn.close()
    return produtos

def salvar_carrinho_pg(user_id, carrinho):
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO carrinhos (user_id, carrinho) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET carrinho = EXCLUDED.carrinho;",
        (user_id, json.dumps(carrinho))
    )
    conn.commit()
    cur.close()
    conn.close()

def obter_carrinho_pg(user_id):
    conn = conectar_db()
    cur = conn.cursor()
    cur.execute("SELECT carrinho FROM carrinhos WHERE user_id = %s;", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return json.loads(row[0])
    return {}

# ====================================
# ✅ COMANDOS PRINCIPAIS
# ====================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛒 Olá! Use /carrinho para ver seus itens!")

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operação cancelada!")
    return ConversationHandler.END
    
async def cadastrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text("📌 Nome do produto?")
    return NOME

async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome"] = update.message.text
    await update.message.reply_text("✏️ Descrição do produto?")
    return DESCRICAO

async def receber_descricao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["descricao"] = update.message.text
    await update.message.reply_text("💴 Preço em ienes?")
    return PRECO

async def receber_preco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        preco = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Digite um número.")
        return PRECO

    context.user_data["preco"] = preco
    await update.message.reply_text(f"📸 Envie a foto.")
    return FOTO

async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto = update.message.photo[-1].file_id
    produto = {
        "nome": context.user_data["nome"],
        "descricao": context.user_data["descricao"],
        "preco": context.user_data["preco"],
        "foto": foto
    }
    salvar_produto_pg(produto)
    link = f"https://t.me/{BOT_USERNAME}?start={produto['nome']}"
    botao = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Comprar", url=link)]])

    await context.bot.send_photo(chat_id=GROUP_USERNAME, photo=foto,
        caption=f"*{produto['nome']}*\n_{produto['descricao']}_\n\n"
                f"🇯🇵¥{produto['preco']} | 🇧🇷R${produto['preco']*VALOR_IENE_REAL:.2f}",
        parse_mode="Markdown", reply_markup=botao)

    await update.message.reply_text("✅ Produto cadastrado e enviado!")
    return ConversationHandler.END

# ====================================
# ✅ CARRINHO
# ====================================
async def ver_carrinho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    produtos = obter_produtos_pg()
    carrinho = obter_carrinho_pg(user_id)
    if not carrinho:
        await update.message.reply_text("🛒 Seu carrinho está vazio.")
        return

    texto = "🛒 *Seu carrinho:*\n\n"
    botoes = []
    total_iene = 0

    for id_produto, qtd in carrinho.items():
        produto = produtos[id_produto]
        subtotal = produto["preco"] * qtd
        total_iene += subtotal
        texto += f"{qtd} × {produto['nome']}\n"
        botoes.append([
            InlineKeyboardButton("+1", callback_data=f"mais:{id_produto}"),
            InlineKeyboardButton("-1", callback_data=f"menos:{id_produto}")
        ])
        botoes.append([InlineKeyboardButton("❌ Cancelar item", callback_data=f"cancelar:{id_produto}")])

    total_servico = total_iene * TAXA_SERVICO
    total_final = total_iene + total_servico
    total_real = total_final * VALOR_IENE_REAL

    texto += "───────────────\n"
    texto += f"\n🧾*Subtotal:* ¥{total_iene:,}".replace(",", ".") + f" | R$ {total_iene * VALOR_IENE_REAL:.2f}"
    texto += f"\n💼*Taxa de serviço (20%):* ¥{int(total_servico):,}".replace(",", ".") + f" | R$ {total_servico * VALOR_IENE_REAL:.2f}"
    texto += f"\n\n✅*Total: ¥{int(total_final):,}".replace(",", ".") + f" | R$ {total_real:.2f}*"

    botoes.append([
        InlineKeyboardButton("✅ Finalizar compra", callback_data="finalizar_compra"),
        InlineKeyboardButton("❌ Cancelar pedido", callback_data="cancelar_pedido")
    ])

    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))

async def carrinho_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    produtos = obter_produtos_pg()
    carrinho = obter_carrinho_pg(user_id)
    data = query.data

    if data.startswith("mais:"):
        id_produto = data.split(":")[1]
        carrinho[id_produto] = carrinho.get(id_produto, 0) + 1
    elif data.startswith("menos:"):
        id_produto = data.split(":")[1]
        if carrinho[id_produto] > 1:
            carrinho[id_produto] -= 1
    elif data.startswith("cancelar:"):
        id_produto = data.split(":")[1]
        carrinho.pop(id_produto, None)
    elif data == "cancelar_pedido":
        carrinho = {}
        await query.edit_message_text("❌ Pedido cancelado. Carrinho esvaziado!")
        salvar_carrinho_pg(user_id, carrinho)
        return
    elif data == "finalizar_compra":
        await query.message.reply_text(
            f"📝 Nome completo?\n📍 Não tem suíte? Cadastre aqui: {URL_FORMULARIO}",
            parse_mode="Markdown"
        )
        return 1

    salvar_carrinho_pg(user_id, carrinho)
    await ver_carrinho(update, context)

# ====================================
# ✅ COLETA DE DADOS CLIENTE
# ====================================
async def receber_nome_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cadastro_temp[update.effective_user.id] = {"nome": update.message.text}
    await update.message.reply_text("📦 Informe sua suíte.")
    return 2

async def receber_suite_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cadastro_temp[update.effective_user.id]["suite"] = update.message.text
    await update.message.reply_text("📱 Telefone com DDD?")
    return 3

async def receber_telefone_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cadastro_temp[update.effective_user.id]["telefone"] = update.message.text
    await update.message.reply_text("📧 Seu e-mail?")
    return 4

async def receber_email_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cadastro_temp[update.effective_user.id]["email"] = update.message.text
    await update.message.reply_text(
        f" *Formas de Pagamento*\n\n"
        f"💳 *Pagamento via Pix*\n🔑 Chave: `{CHAVE_PIX}`\n\n"
        f"💳 *Parcelamento no cartão?* Fale no WhatsApp!\n"
        f"💸 *Wise disponível para transferência internacional.*\n\n"
        f"📲 Dúvidas? [Clique aqui]({URL_WHATSAPP})",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ====================================
# ✅ FLASK & WEBHOOK
# ====================================
app_flask = Flask(__name__)

@app_flask.route("/", methods=["GET"])
def home():
    return "Bot está online!"

@app_flask.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return "OK"
    
bot_app = ApplicationBuilder().token(TOKEN).build()

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("carrinho", ver_carrinho))
bot_app.add_handler(CallbackQueryHandler(carrinho_callback))

conv_cadastro = ConversationHandler(
    entry_points=[CommandHandler("cadastrar", cadastrar)],
    states={
        NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
        DESCRICAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_descricao)],
        PRECO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_preco)],
        FOTO: [MessageHandler(filters.PHOTO, receber_foto)]
    },
    fallbacks=[CommandHandler("cancelar", cancelar)]
)
bot_app.add_handler(conv_cadastro)

conv_cliente = ConversationHandler(
    entry_points=[CallbackQueryHandler(carrinho_callback, pattern="^finalizar_compra$")],
    states={
        1: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_cliente)],
        2: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_suite_cliente)],
        3: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_telefone_cliente)],
        4: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_email_cliente)],
    },
    fallbacks=[]
)
bot_app.add_handler(conv_cliente)


if __name__ == "__main__":
    import nest_asyncio
    import asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_app.initialize())
    loop.run_until_complete(bot_app.start())
    loop.run_until_complete(bot_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook"))

    app_flask.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
