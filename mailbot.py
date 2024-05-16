import imaplib
import email
import time
import smtplib, ssl
import configparser
import codecs
import os
from email.mime.multipart import MIMEMultipart, MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.encoders import encode_base64
from datetime import datetime
import logging
from systemd.journal import JournalHandler


#log habdler
log = logging.getLogger('mailbot')
log.addHandler(JournalHandler())
log.setLevel(logging.INFO)

#Global vars
ini = ''
mail_user = ''
mail_passwd = ''
imap_host = ''
smtp_host = ''
smtp_port = ''

def create_body(html_path,msg):
    result = ''
    attachments = []
    text_body = 'This email had no text'
    html_text = ''
    body = 'This email had no text'
    if len(html_path) >0 and html_path != 'none':
        html_text = read_file(html_path)        
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            try:
                body = part.get_payload(decode=True).decode()
            except:
                pass
            if content_type == "text/plain" and "attachment" not in content_disposition:
                text_body = body
            elif "attachment" in content_disposition:
                    attachments.append(part.get_filename())
    else:
        content_type = msg.get_content_type()
        body = msg.get_payload(decode=True).decode()
        if content_type == "text/plain":
            text_body = body
            print(body)
        if content_type == "text/html":
            print('==Single part html body == ')
            text_body = body
            print(body)
    result +=html_text
    result += '<br>=== Original message ===<br>'
    if len(text_body) ==0:
        result+='<ul><li>No text message</li></ul>'
    else:
        result += text_body
    result +='<br>=== Attachments ==='
    result +='<ul>'
    if len(attachments) == 0:
        result +='<li>No attachments</li>'
    for a in attachments:
        result += '<li>'+a+'</li>'
    result +='</ul>'
    return result

def read_file(writepath):
    text = ''
    if os.path.exists(writepath):
        pass
    else:
        append_file(writepath,'')
    with codecs.open(writepath, encoding='utf-8') as f:
        for line in f:
            text+=line
    return text

def append_file(writepath,text):
    mode = 'a' if os.path.exists(writepath) else 'w'
    with open(writepath, mode) as f:
        f.write(text)

def load_credentials():
    global mail_user, mail_passwd, imap_host, smtp_host, smtp_port
    ini = configparser.ConfigParser()
    ini.read('config/mail_config.ini')
    mail_user = ini.get('config','mail_user')
    mail_passwd = ini.get('config','mail_passwd')
    imap_host = ini.get('config','imap_host')
    smtp_host = ini.get('config','smtp_host')
    smtp_port = ini.get('config','smtp_port')

def load_bot_config():
    global ini
    ini = configparser.ConfigParser()
    ini.read('config/bot_config.ini')

def mail_connect():
    load_bot_config()
    load_credentials()
    imap_server = imaplib.IMAP4_SSL(host=imap_host)
    imap_server.login(mail_user, mail_passwd)
    imap_server.select()  # Default is `INBOX`
    return imap_server

def move_mail(imap,msg_uid,dest_folder):
    result = imap.uid('COPY', msg_uid, dest_folder)
    print('Result: ',result)
    if result[0] == 'OK':
        mov, data = imap_server.uid('STORE', msg_uid , '+FLAGS', '(\Deleted)')
        imap_server.expunge()
def print_datetime():
    log.info(get_datetime())

def get_datetime():
    now = datetime.now()
    return now.strftime("%d/%m/%Y %H:%M:%S")
    

def print_message(message,message_number):
    log.info('====== New mail subject rule match  =========')
    log.info('Sent: '+message["Date"])
    log.info(f'From: {message["from"]}')
    log.info(f'To: {message["to"]}')
    log.info(f'Subject: {message["subject"]}')
    
        

def load_mail(imap_server, search):
    _, message_numbers_raw = imap_server.uid('search', None, search)
    for message_number in message_numbers_raw[0].split():
        _, msg = imap_server.uid('fetch',message_number, '(RFC822)')        
        message = email.message_from_bytes(msg[0][1])
        process_rules(message,message_number)


def process_rules(message,message_number):
    mail_from = message['from']
    mail_from = mail_from.split('<')
    mail_from = mail_from[-1]
    mail_from=mail_from.replace('>','')
    #log.info('###############################')
    #log.info("Message Found from: "+mail_from)
    #log.info("Subject: "+message['subject'])
    #log.info('Date: '+message['Date'])
    for section in ini.sections():
        filter_type = ini.get(section,'filter_type')
        subject = ini.get(section,'subject')
        move_message = ini.get(section,'move_message')
        move_to = ini.get(section,'move_to')
        black_list_path = ini.get(section,'black_list_path')
        black_list = ''
        if black_list_path != 'none':
            black_list = read_file(black_list_path)
        html_path = ini.get(section,'html_text')
        html_text = ''
        image = ini.get(section,'image')
        image = image.split('|')


        #here we go
        if filter_type == 'subject':
            #if subject.upper() in message['subject'].upper():
            if message['subject'].upper().startswith(subject.upper()):
                print_message(message, message_number)
                html_text = create_body(html_path,message)
                print('Preparing to send email')
                dest = []
                dest.append(message['from'])
                send_mail(dest,message['subject'],html_text,image)
                if move_message=='yes':
                    move_mail(imap_server,message_number,move_to)
                if black_list_path != 'none' and mail_from not in black_list:
                    append_file(black_list_path,mail_from+';\n')
                log.info('Action: Mail accepted')
                return

        if filter_type == 'black_list':
            #if mail_from in black_list and subject not in message['subject']:
            if mail_from in black_list and not  message['subject'].upper().startswith(subject.upper()):
                print_message(message, message_number)
                log.info('Black listing message')
                html_text = create_body(html_path,message)
                print('Preparing to send email')
                dest = []
                dest.append(message['from'])
                send_mail(dest,message['subject'],html_text,image)
                if move_message=='yes':
                    move_mail(imap_server,message_number,move_to)
                log.info('Action: Mail blacklisted')
                return 

def send_mail(to_emails,subject, msg_html_body,images):
    email_message = MIMEMultipart()
    email_message.add_header('To', ', '.join(to_emails))
    email_message.add_header('From', mail_user)
    email_message.add_header('Subject', 'BOT REPLY: '+subject)
    email_message.add_header('X-Priority', '1')  # Urgent/High priority
    #text_part = MIMEText('Hello world plain text!', 'plain')
    html_part = MIMEText(msg_html_body, 'html')
    email_message.attach(html_part)
    image_count=1
    for image in images:
        image = MIMEImage(open(image, 'rb').read())
        image.add_header('Content-ID', '<image'+str(image_count)+'>')
        email_message.attach(image)
        image_count +=1
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()  # Can be omitted
        server.starttls(context=context)
        server.ehlo()  # Can be omitted
        server.login(mail_user, mail_passwd)
        server.sendmail(mail_user, to_emails, email_message.as_bytes())
        server.quit()
    print('Mail sent')

print('STARTING MAILBOT')
print('=================================')
while True:
    try:
        log.info("##############################   LOOPING ############################")
        #print_datetime()
        append_file('logs/running.log','\n'+get_datetime())
        imap_server = mail_connect()
        load_mail(imap_server, 'All')
        #load_mail(imap_server, 'SUBJECT "IT"')
        log.info("End of loop")
    except Exception as e: 
        log.error("!!!!!!!!!!!!!!!!!!!!!!!!!!! Loop error !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        log.info(e)
        #print_datetime()
        print(e)
    time.sleep(60)


    

