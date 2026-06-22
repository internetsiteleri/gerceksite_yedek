import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token'ı .env'den al
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    raise ValueError("BOT_TOKEN ortam değişkeni ayarlanmamış!")

# Veritabanı dosyası
DATA_FILE = "scheduled_posts.json"
MEDIA_FOLDER = "media_files"

# Zaman dilimi
TIMEZONE = pytz.timezone('Europe/Istanbul')

# Scheduler
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

class PostScheduler:
    def __init__(self):
        self.posts = []
        self.load_posts()
        self.setup_folders()
        self.schedule_existing_posts()
        
    def setup_folders(self):
        if not os.path.exists(MEDIA_FOLDER):
            os.makedirs(MEDIA_FOLDER)
            
    def load_posts(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.posts = json.load(f)
                    print(f"📂 {len(self.posts)} gönderi yüklendi")
            except:
                self.posts = []
        else:
            self.posts = []
            
    def save_posts(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.posts, f, ensure_ascii=False, indent=2)
        print(f"💾 {len(self.posts)} gönderi kaydedildi")
            
    def add_post(self, chat_id, chat_type, scheduled_time, file_path, caption, file_type):
        post_id = len(self.posts) + 1
        post = {
            'id': post_id,
            'chat_id': chat_id,
            'chat_type': chat_type,
            'scheduled_time': scheduled_time,
            'file_path': file_path,
            'caption': caption,
            'file_type': file_type,
            'status': 'pending'
        }
        self.posts.append(post)
        self.save_posts()
        self.schedule_post(post)
        print(f"✅ Gönderi eklendi! ID: {post_id}")
        return post_id
        
    def schedule_post(self, post):
        try:
            scheduled_time = datetime.fromisoformat(post['scheduled_time'])
            if scheduled_time > datetime.now(TIMEZONE):
                trigger = DateTrigger(run_date=scheduled_time, timezone=TIMEZONE)
                scheduler.add_job(
                    self.send_post,
                    trigger=trigger,
                    args=[post['id']],
                    id=f"post_{post['id']}",
                    replace_existing=True
                )
                print(f"⏰ Gönderi {post['id']} zamanlandı: {scheduled_time.strftime('%H:%M')}")
        except Exception as e:
            print(f"❌ Zamanlama hatası: {e}")
            
    def schedule_existing_posts(self):
        for post in self.posts:
            if post['status'] == 'pending':
                self.schedule_post(post)
                
    async def send_post(self, post_id):
        try:
            post = None
            for p in self.posts:
                if p['id'] == post_id:
                    post = p
                    break
                    
            if not post or post['status'] == 'sent':
                return
                
            app = application_instance
            if not app:
                return
                
            file_path = post['file_path']
            if not os.path.exists(file_path):
                post['status'] = 'failed'
                self.save_posts()
                return
                
            chat_id = post['chat_id']
            caption = post.get('caption', '')
            file_type = post['file_type']
            
            print(f"📤 Gönderi {post_id} gönderiliyor...")
            
            with open(file_path, 'rb') as f:
                if file_type == 'photo':
                    await app.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)
                elif file_type == 'video':
                    await app.bot.send_video(chat_id=chat_id, video=f, caption=caption)
                elif file_type == 'audio':
                    await app.bot.send_audio(chat_id=chat_id, audio=f, caption=caption)
                elif file_type == 'document':
                    await app.bot.send_document(chat_id=chat_id, document=f, caption=caption)
                    
            post['status'] = 'sent'
            self.save_posts()
            print(f"✅ Gönderi {post_id} gönderildi!")
            
        except Exception as e:
            print(f"❌ Gönderi hatası: {e}")
            if post:
                post['status'] = 'failed'
                self.save_posts()
                
    def delete_post(self, post_id):
        self.posts = [p for p in self.posts if p['id'] != post_id]
        self.save_posts()
        try:
            scheduler.remove_job(f"post_{post_id}")
        except:
            pass
        print(f"🗑️ Gönderi {post_id} silindi")

post_scheduler = PostScheduler()
application_instance = None

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_identifier):
    try:
        if chat_identifier.startswith('@'):
            chat = await context.bot.get_chat(chat_identifier)
            print(f"🔍 Chat bulundu: {chat.id}")
            return chat.id
        elif chat_identifier.isdigit():
            return int(chat_identifier)
        return None
    except Exception as e:
        print(f"❌ Chat bulunamadı: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.bot_data.get('admin_id'):
        context.bot_data['admin_id'] = user.id
        
    await update.message.reply_text(f"""
🎯 Merhaba {user.first_name}!

Ben Zamanlayıcı Bot - belirlediğiniz tarih ve saatte kanal/grup paylaşımları yaparım.

📋 Kullanım komutları:

/yeni - Yeni gönderi oluştur
/liste - Bekleyen gönderileri listele
/sil <id> - Gönderiyi sil
/iptal - İşlemi iptal et
/skip - Açıklamayı atla

⚠️ ÖNEMLİ: 
• Bot kanalda admin olmalı!
• Tarih formatı: YYYY-MM-DD HH:MM
• Zaman Türkiye saatine göre (UTC+3)
    """)

async def new_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['step'] = 'waiting_chat'
    context.user_data['post_data'] = {}
    
    await update.message.reply_text(
        "📝 Yeni gönderi oluşturuyoruz...\n\n"
        "1️⃣ Paylaşılacak kanal veya grup username'ini @ ile girin:\n"
        "Örnek: @kanal_adi"
    )

async def list_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending_posts = [p for p in post_scheduler.posts if p['status'] == 'pending']
    
    if not pending_posts:
        await update.message.reply_text("📭 Bekleyen gönderi bulunmuyor.")
        return
        
    message = "📋 BEKLEYEN GÖNDERİLER:\n\n"
    for post in pending_posts:
        scheduled_time = datetime.fromisoformat(post['scheduled_time'])
        formatted_time = scheduled_time.strftime("%d.%m.%Y %H:%M")
        message += f"ID: {post['id']}\n"
        message += f"📍 {post['chat_type']}: {post['chat_id']}\n"
        message += f"⏰ {formatted_time}\n"
        message += f"📎 {post['file_type']}\n"
        if post.get('caption'):
            message += f"📝 {post['caption'][:50]}...\n"
        message += "─" * 30 + "\n"
            
    await update.message.reply_text(message)

async def delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        post_id = int(context.args[0])
        post_scheduler.delete_post(post_id)
        await update.message.reply_text(f"✅ {post_id} numaralı gönderi silindi.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Kullanım: /sil <gönderi_id>")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ İşlem iptal edildi.")

async def skip_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step')
    
    if step != 'waiting_caption':
        await update.message.reply_text("⚠️ Açıklama aşamasında değilsiniz.")
        return
        
    post_data = context.user_data.get('post_data', {})
    post_data['caption'] = ''
    
    try:
        chat_id = await get_chat_id(update, context, post_data['chat_id'])
        if not chat_id:
            await update.message.reply_text("❌ Geçersiz kanal/grup!")
            return
            
        print(f"📝 Kaydediliyor (boş): {post_data}")
            
        post_id = post_scheduler.add_post(
            chat_id=chat_id,
            chat_type=post_data['chat_type'],
            scheduled_time=post_data['scheduled_time'],
            file_path=post_data['file_path'],
            caption='',
            file_type=post_data['file_type']
        )
        
        scheduled_time = datetime.fromisoformat(post_data['scheduled_time'])
        
        await update.message.reply_text(
            f"✅ GÖNDERİ ZAMANLANDI!\n\n"
            f"📋 ID: {post_id}\n"
            f"📍 Hedef: {post_data['chat_id']}\n"
            f"⏰ Zaman: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"📎 Tür: {post_data['file_type']}\n"
            f"📝 Açıklama: (boş)\n\n"
            f"ℹ️ /liste ile görebilirsiniz."
        )
        
        context.user_data.clear()
        
    except Exception as e:
        print(f"❌ HATA: {e}")
        await update.message.reply_text(f"❌ Hata: {e}")

# TEK BİR HANDLER - TÜM İŞLEMLER BURADA
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm mesajları ve medyaları işle"""
    step = context.user_data.get('step')
    
    print(f"🔍 Adım: {step}")
    
    # --- MEDYA KONTROLÜ ---
    if update.message.photo or update.message.video or update.message.audio or update.message.document:
        if step == 'waiting_media':
            post_data = context.user_data.get('post_data', {})
            file_type = None
            file_path = None
            
            try:
                if update.message.photo:
                    file_type = 'photo'
                    file = await update.message.photo[-1].get_file()
                    file_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                elif update.message.video:
                    file_type = 'video'
                    file = await update.message.video.get_file()
                    file_name = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                elif update.message.audio:
                    file_type = 'audio'
                    file = await update.message.audio.get_file()
                    file_name = f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                elif update.message.document:
                    file_type = 'document'
                    file = await update.message.document.get_file()
                    file_name = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{update.message.document.file_name}"
                else:
                    await update.message.reply_text("❌ Desteklenmeyen dosya türü!")
                    return
                    
                file_path = os.path.join(MEDIA_FOLDER, file_name)
                await file.download_to_drive(file_path)
                
                post_data['file_path'] = file_path
                post_data['file_type'] = file_type
                context.user_data['step'] = 'waiting_caption'
                context.user_data['post_data'] = post_data
                
                print(f"✅ Dosya indirildi: {file_type}")
                
                await update.message.reply_text(
                    f"✅ Dosya başarıyla yüklendi: {file_type}\n\n"
                    "4️⃣ Açıklama yazın veya /skip yapın"
                )
                
            except Exception as e:
                print(f"❌ Dosya hatası: {e}")
                await update.message.reply_text(f"❌ Dosya yüklenirken hata: {e}")
        else:
            await update.message.reply_text("⚠️ Önce /yeni komutunu kullanın!")
        return
    
    # --- METİN MESAJLARI ---
    if not update.message.text:
        return
        
    text = update.message.text.strip()
    
    # AÇIKLAMA GİRİŞİ
    if step == 'waiting_caption':
        post_data = context.user_data.get('post_data', {})
        post_data['caption'] = text
        
        try:
            chat_id = await get_chat_id(update, context, post_data['chat_id'])
            if not chat_id:
                await update.message.reply_text("❌ Geçersiz kanal/grup!")
                return
                
            print(f"📝 Kaydediliyor: {post_data}")
                
            post_id = post_scheduler.add_post(
                chat_id=chat_id,
                chat_type=post_data['chat_type'],
                scheduled_time=post_data['scheduled_time'],
                file_path=post_data['file_path'],
                caption=text,
                file_type=post_data['file_type']
            )
            
            scheduled_time = datetime.fromisoformat(post_data['scheduled_time'])
            
            await update.message.reply_text(
                f"✅ GÖNDERİ ZAMANLANDI!\n\n"
                f"📋 ID: {post_id}\n"
                f"📍 Hedef: {post_data['chat_id']}\n"
                f"⏰ Zaman: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"📎 Tür: {post_data['file_type']}\n"
                f"📝 Açıklama: {text}\n\n"
                f"ℹ️ /liste ile görebilirsiniz."
            )
            
            context.user_data.clear()
            
        except Exception as e:
            print(f"❌ HATA: {e}")
            await update.message.reply_text(f"❌ Hata: {e}")
        return
    
    # KANAL/GIRIŞ
    if step == 'waiting_chat':
        if text.startswith('@'):
            context.user_data['post_data']['chat_id'] = text
            context.user_data['post_data']['chat_type'] = 'grup'
            context.user_data['step'] = 'waiting_time'
            await update.message.reply_text(
                f"✅ Hedef belirlendi: {text}\n\n"
                "2️⃣ Paylaşım tarih ve saatini girin:\n"
                "Format: YYYY-MM-DD HH:MM\n"
                "Örnek: 2024-12-31 23:59"
            )
        else:
            await update.message.reply_text("❌ Geçersiz format! @ ile başlayın.")
        return
    
    # TARİH GİRİŞİ
    if step == 'waiting_time':
        try:
            scheduled_time = datetime.strptime(text, "%Y-%m-%d %H:%M")
            scheduled_time = TIMEZONE.localize(scheduled_time)
            
            if scheduled_time <= datetime.now(TIMEZONE):
                await update.message.reply_text("❌ Geçmiş tarih! İleri bir tarih girin.")
                return
                
            context.user_data['post_data']['scheduled_time'] = scheduled_time.isoformat()
            context.user_data['step'] = 'waiting_media'
            
            await update.message.reply_text(
                f"✅ Zaman belirlendi: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n\n"
                "3️⃣ Şimdi paylaşılacak dosyayı gönderin:\n"
                "• Resim, Video, Ses veya Dosya gönderebilirsiniz."
            )
        except ValueError:
            await update.message.reply_text("❌ Geçersiz format! YYYY-MM-DD HH:MM")
        return
    
    # BAŞKA BİR ADIM YOKSA
    await update.message.reply_text("⚠️ Bir işlem yok. /yeni ile başlayın.")

def main():
    global application_instance
    
    application = Application.builder().token(TOKEN).build()
    application_instance = application
    
    # Komut handler'ları
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("yeni", new_post))
    application.add_handler(CommandHandler("liste", list_posts))
    application.add_handler(CommandHandler("sil", delete_post))
    application.add_handler(CommandHandler("iptal", cancel))
    application.add_handler(CommandHandler("skip", skip_caption))
    
    # TEK BİR MESAJ HANDLER
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.Document.ALL, 
        handle_all_messages
    ))
    
    scheduler.start()
    
    print("🚀 Bot başlatıldı!")
    print(f"🤖 Token: {TOKEN[:10]}...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()