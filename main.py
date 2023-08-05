import csv
import os

import requests
from dotenv import load_dotenv
from slack_bolt import App
from slack_sdk.scim import SCIMClient, User
from slack_sdk.scim.v1.user import UserName, UserEmail, UserPhoneNumber

load_dotenv()

TOKEN = os.environ['TOKEN']
app = App(token=TOKEN)
scim_client = SCIMClient(token=TOKEN)
headers = {'Authorization': f'Bearer {TOKEN}'}

GROUPS_MAP = {
    "coaches": 'S05E07Y6F6Z',
    "hitters": 'S05ESTCTXDE',
    "pitchers": 'S05DWGMM2B0',
}


def add_user_to_group(user_id, group_name):
    group_id = GROUPS_MAP.get(group_name.lower())
    if group_id:
        group_url = f'https://api.slack.com/scim/v2/Groups/{group_id}'
        group_result = requests.get(group_url, headers=headers)
        group_data = group_result.json()
        members = group_data['members']
        members.append({'value': user_id})
        data = {
            'schemas': ['urn:ietf:params:scim:api:messages:2.0:PatchOp'],
            'Operations': [{'op': 'replace', 'path': 'members', 'value': members}]
        }
        requests.patch(group_url, headers=headers, json=data)


def add_user_to_slack(first_name, last_name, title, email, phone, user_type, year=None, birthday=None,
                      user_groups=None):
    response = scim_client.search_users(filter=f'userName eq "{email}"', start_index=1, count=1)
    users = response.users

    user = User(
        user_name=f'{email}',
        name=UserName(given_name=first_name, family_name=last_name),
        display_name='',
        title=title,
        emails=[UserEmail(value=email)],
        phone_numbers=[UserPhoneNumber(value=phone)]
    )

    if user_type == 'STAFF':
        user.display_name = f'Coach {last_name}'

    if users and len(users) > 0:
        print(f'❗️{first_name} {last_name} already exists so this will only update the user')
        existing_user = users[0]
        user.id = existing_user.id
        user_id = scim_client.update_user(user).user.id
    else:
        user_id = scim_client.create_user(user).user.id

    if user_type != 'STAFF':
        custom_fields = {
            'fields': {
                'Xf05DNLNQQ0P': {'value': year, 'alt': ''},
                'Xf05FH4RDALB': {'value': birthday, 'alt': ''}
            }
        }
        app.client.users_profile_set(user=user_id, profile=custom_fields)

    if user_groups:
        for group in user_groups:
            add_user_to_group(user_id, group)


def process_row(csv_row):
    first_name = csv_row.get('first_name')
    last_name = csv_row.get('last_name')
    user_type = csv_row.get('type')
    title = csv_row.get('title')
    email = csv_row.get('email')
    phone = csv_row.get('phone')
    year = csv_row.get('year')
    birthday = csv_row.get('birthday')
    groups = csv_row.get('groups')

    if first_name and last_name:
        print(f'🟡 Beginning to process user with name {first_name} {last_name}')
    else:
        print('🔴 Error processing this user because there is no first and or last name')
        return

    if user_type:
        if user_type == 'PLAYER':
            if not year or not birthday:
                print('🔴 Error processing because the player is missing their year, birthday, or both')
                return
        elif user_type != 'STAFF':
            print('🔴 Error processing because the type is not PLAYER or STAFF')
            return
    else:
        print('🔴 Error processing this user because there is no type')
        return

    if not title or not email or not phone:
        print('🔴 Error processing because there is not title, email, phone, or a combination of values')
        return

    groups = groups.split(',') if groups else None

    add_user_to_slack(first_name, last_name, title, email, phone, user_type, year, birthday, groups)

    print(f'🟢 Successfully added or updated user {first_name} {last_name} in Slack\n')


print('⚾️⚾️⚾️ Cajuns Baseball Slack User Importer Tool ⚾️⚾️⚾️')

file_name = input('\n\nEnter the file name of the CSV: ')

try:
    with open(file_name, mode='r') as file:
        csv_reader = csv.DictReader(file)
        rows = list(csv_reader)
        print(f'\n📢 Beginning to import {len(rows)} user/s')
        for row in rows:
            process_row(row)
except FileNotFoundError:
    print(f'\nSorry 😢 there was no file found with name {file_name}')
