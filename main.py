import mysql.connector
import argparse
import os
import csv
import datetime
import private.config
import smtplib
from os.path import basename
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate


def get_all_users():
    connection = mysql.connector.connect(**private.config.DATABASE_CONFIG)
    cursor = connection.cursor()
    query = ("SELECT id, first_name, last_name, hex(mac), inet_ntoa(ip) FROM %s" % private.config.TABLE_NAME)
    cursor.execute(query)

    user_list = cursor.fetchall()

    connection.close()

    return user_list

def format_printable_mac(mac):
    # Format MAC from AABBCC112233 to AA:BB:CC:11:22:33
    mac = str.upper(mac)
    return ':'.join(mac[i:i+2] for i in range(0, len(mac), 2))

def print_user_details():
    user_list = get_all_users()
    for user in user_list:
        print(user[0], user[1], user[2], format_printable_mac(user[3]), user[4])

def add_new_user():
    # Inputs
    first_name = input("First name: ")
    last_name = input("Last name: ")
    mac = input("MAC: ")

    # Insert query
    query = ("INSERT INTO clients" # TO DO change to table_name
             "(first_name, last_name, ip, mac)" 
             "VALUES (%(first_name)s, %(last_name)s, IFNULL((SELECT MAX(t.ip)+1 FROM clients AS t), INET_ATON(%(start_ip)s)), UNHEX(%(mac)s))")
    data_query = {
        'table_name' : private.config.TABLE_NAME,
        'first_name' : first_name,
        'last_name' : last_name,
        'start_ip' : private.config.START_IP,
        'mac' : mac
    }

    # Open connection, execute query and commit changes
    connection = mysql.connector.connect(**private.config.DATABASE_CONFIG)
    cursor = connection.cursor()
    cursor.execute(query, data_query)
    connection.commit()

    cursor.close()
    connection.close()

def get_active_users():
    # Open SQL connection
    connection = mysql.connector.connect(**private.config.DATABASE_CONFIG)
    cursor = connection.cursor()

    # Select all users
    query = ("SELECT id, first_name, last_name, hex(mac), inet_ntoa(ip) FROM %s WHERE is_active = 1" % private.config.TABLE_NAME)
    cursor.execute(query)
    user_list = cursor.fetchall()

    connection.close()

    return user_list

def generate_user_list_file():
    # Get all users
    print("Gettin users from database...")
    user_list = get_active_users()

    # Open file and save dhcp clients list.
    user_list_file = open(private.config.PATH_TO_USER_LIST_FILE, "w")
    print("Creating new file %s" % private.config.PATH_TO_USER_LIST_FILE)
    user_id = 1

    for user in user_list:
        user_list_file.write("#######################################\n")
        user_list_file.write("# Name : " + user[1] + "\n")
        user_list_file.write("# Surname : " + user[2] + "\n")
        user_list_file.write("host ID_B" + str(user_id) + ".1\n")
        user_list_file.write("{\n")
        user_list_file.write("hardware ethernet " + format_printable_mac(user[3]) + ";\n")
        user_list_file.write("fixed-address " + user[4] + ";\n")
        user_list_file.write("}\n\n")
        print("%i" % user[0], end='\r')
        user_id = user_id + 1
            
    user_list_file.close()
    print("%i users has been added." % user_id)

    # Restart DHCP service
    restart_dhcp = ("service isc-dhcp-server restart")
    os.system(restart_dhcp)

def clean_user_list():
    # Open SQL connection
    connection = mysql.connector.connect(**private.config.DATABASE_CONFIG)
    cursor = connection.cursor()

    # Removing all users from database
    print("Removing all records...")
    query = ("DELETE from %s" % private.config.TABLE_NAME)
    cursor.execute(query)
    connection.commit()

    # Reset auto increment to 1
    print("Resetting auto increment to 1...")
    query = ("ALTER TABLE `%s` MODIFY `id` int(11) NOT NULL AUTO_INCREMENT,AUTO_INCREMENT=1;" % private.config.TABLE_NAME)
    cursor.execute(query)
    connection.commit()

    connection.close()
    print("Done. Remember to add someone before restart!")

def generate_report():
    # Get all users
    print("Gettin user list...")
    user_list = get_all_users()

    # Construct file name
    print("Generating monthly report...")
    full_date = datetime.datetime.now()
    date = full_date.strftime("%m.%Y")
    file_name = private.config.PATH_MONTHLY_REPORTS + private.config.SH_NAME + date + ".csv"

    # Save to CSV
    with open(file_name, 'w', newline='') as write_file:
        writer = csv.writer(write_file)
        for user in user_list:
            writer.writerow([user[0], user[1], user[2], user[4], format_printable_mac(user[3])]) # Id, First Name, Last Name, MAC, IP
    write_file.close()
    print("Report has been generated: %s" % file_name)

    return file_name

def send_monthly_report():
    # Construct mail variables
    now = datetime.datetime.now()
    date_time = now.strftime("%m/%d/%Y, %H:%M:%S")
    mail_body = 'Lista IP wygenerowana ' + date_time

    # Generate user list
    user_list_file = generate_report()

    # Construct message
    msg = MIMEMultipart()
    msg['From'] = private.config.SMTP_USERNAME
    msg['To'] = private.config.MAIL_TO
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = private.config.MAIL_SUBJECT

    msg.attach(MIMEText(mail_body))

    with open(user_list_file, "rb") as fil:
        part = MIMEApplication(
            fil.read(),
            Name=basename(user_list_file)
        )
        # After the file is closed
    part['Content-Disposition'] = 'attachment; filename="%s"' % basename(user_list_file)
    msg.attach(part)


    smtp = smtplib.SMTP(private.config.SMTP_SERVER, private.config.SMTP_PORT)
    smtp.starttls()
    smtp.login(private.config.SMTP_USERNAME, private.config.SMTP_PASSWORD)
    smtp.sendmail(private.config.SMTP_USERNAME, private.config.MAIL_TO, msg.as_string())
    smtp.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", help="Select one of the following action: list, add, restart, clean, report")
    args = parser.parse_args()

    if args.action == "list":
        print_user_details()
    elif args.action == "add":
        add_new_user()
    elif args.action == "restart":
        generate_user_list_file()
    elif args.action == "clean":
        clean_user_list()
    elif args.action == "report":
        generate_report()
    elif args.action == "email":
        send_monthly_report()

if __name__ == '__main__':
    main()