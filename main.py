import os

import functions_framework
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


def sync_user_with_slack(first_name, last_name, title, email, phone, user_type, enable, year=None, birthday=None,
                         user_groups=None):
    response = scim_client.search_users(filter=f'userName eq "{email}"', start_index=1, count=1)
    users = response.users

    user = User(
        user_name=f'{email}',
        name=UserName(given_name=first_name, family_name=last_name),
        display_name='',
        title=title,
        emails=[UserEmail(value=email)],
        phone_numbers=[UserPhoneNumber(value=phone)],
        active=True
    )

    if user_groups and 'coaches' in user_groups:
        user.display_name = f'Coach {last_name}'

    if users and len(users) > 0:
        print(f'❗️{first_name} {last_name} already exists so this will only update the user')
        existing_user = users[0]

        if not enable:
            print('❗❗❗This user has been set to deactivated and will now be deactivated❗❗❗')
            scim_client.delete_user(existing_user.id)
            return

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


def process_user(body):
    acceptable_types = ['STAFF', 'PLAYER', 'RECRUIT', 'GUEST']
    first_name = body.get('first_name')
    last_name = body.get('last_name')
    user_type = body.get('type')
    title = body.get('title')
    email = body.get('email')
    phone = body.get('phone')
    year = body.get('year')
    birthday = body.get('birthday')
    groups = body.get('groups')
    enable = body.get('enable')

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
        elif user_type not in acceptable_types:
            print(f'🔴 Error processing because the type is not one of {acceptable_types}')
            return
    else:
        print('🔴 Error processing this user because there is no type')
        return

    if not title or not email or not phone:
        print('🔴 Error processing because there is not a title, email, phone, or a combination of these values')
        return

    if enable is None:
        print('🔴 Error processing because the enable value is not set')
        return

    groups = groups.split(',') if groups else None

    sync_user_with_slack(first_name, last_name, title, email, phone, user_type, enable, year, birthday, groups)

    print(f'🟢 Successfully added, updated or disabled user {first_name} {last_name} in Slack\n')


@functions_framework.http
def http_entrypoint(request):
    print('⚾️⚾️⚾️ Cajuns Baseball Slack User Importer Tool ⚾️⚾️⚾️')

    secret = request.headers.get('secret')

    if secret != 'geaux-cajuns':
        print('Unauthorized caller!!! Aborting request')
        return 'UNAUTHORIZED'

    if request.json:
        body = request.json

        for user in body:
            process_user(user)
    else:
        print('Missing JSON body!!! Canceling request')
        return 'BAD_REQUEST'

    return 'OK'
