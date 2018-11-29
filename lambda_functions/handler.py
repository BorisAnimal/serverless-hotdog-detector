import json
import os
import sys
import boto3
from boto3.dynamodb.conditions import Key
import random
import traceback
here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, './vendored'))

import requests


# Gain from evnironment of server
TOKEN = os.environ['TELEGRAM_TOKEN']
ALIAS = os.environ['BOT_ALIAS']
REGION_NAME = os.environ['REGION_NAME']
GAME_STATE_TABLE = os.environ['GAME_STATE_TABLE']
USERS_TABLE = os.environ['USERS_TABLE']
BASE_URL = 'https://api.telegram.org/bot{}'.format(TOKEN)

# Rekognition client
rekognition = boto3.client('rekognition')

# Database tables
database = boto3.resource('dynamodb', region_name=REGION_NAME)
game_state_table = database.Table(GAME_STATE_TABLE)
users_table = database.Table(USERS_TABLE)


# Categories that players can pick
labels_dict = {
    # 'people_and_events': ['Wedding', 'Bride', 'Baby', 'Birthday Cake', 'Guitarist'],
    'food_and_drink': ['Apple', 'Sandwich', 'Wine', 'Cake', 'Pizza', 'Burger', 'Bread', 'Lunch', 
        'Donut', 'Sweets', 'Spaghetti', 'Vermicelli', 'Fries', 'Snack', 'Sushi', 'Hot Dog', 'Soup', 'Juice', 'Mojito', 'Soda'],
    'nature_and_outdoors': ['Beach', 'Mountains', 'Lake', 'Sunset', 'Rainbow', 'Tree', 'Water', 'Waterfall', 'River', 'Cliff', 'Snow', 'Sea'],
    # 'city': ['Downtown', 'Metropolis', 'Park', 'Office Building', 'Tree', 'Street', 'Road', 'Apartment Building']
    'animals_and_pets': ['Dog', 'Cat', 'Horse', 'Tiger', 'Turtle', 'Monkey', 'Panda', 
        'Three-Toed Sloth', 'Fox', 'Zebra', 'Pig', 'Wolf', 'Mouse', 'Owl', 'Duck', 'Bear'],
    'home_and_garden': ['Bed', 'Table', 'Backyard', 'Chandelier', 'Bedroom', 'Plant', 'Chair', 'Cushion', 'Couch', 'Coffee Table', 'Pillow'],
    'sports_and_leisure': ['Golf', 'Basketball', 'Hockey', 'Tennis', 'Hiking', 'Rafting', 'Snowboarding', 'Soccer', 'Swimming', 'Gym', 'Chess', 'Game', 'Gambling'],
    'plants_and_flowers': ['Rose', 'Tulip', 'Palm Tree', 'Forest', 'Bamboo', 'Blossom', 'Anemone', 'Lily', 'Daisies', 'Poppy', 'Gladiolus', 'Cactus'],
    'transportation_and_vehicles': ['Airplane', 'Car', 'Bicycle', 'Motorcycle', 'Truck', 'Ambulance', 
        'Moped', 'Fire Truck', 'Van', 'Helicopter', 'Boat', 'Bus', 'Tractor'],
    'electronics': ['Computer', 'Phone', 'Video Camera', 'TV', 'Headphones', 'Monitor', 
        'Computer Hardware', 'Speaker', 'Electronic Chip', 'Wiring', 'Printer'],
    'celebrities': ['Vladimir Putin', 'Jeff Bezos', 'Morgan Freeman', 'Donald Trump', 'Jackie Chan', 'Leonardo DiCaprio'],
    'random': []
}


# Lambda entry funciton. event - object from Telegram server
def lambda_handler(event, context):
    try:
        request = json.loads(event['body'])['message']
        # Just for debug
        # print('request: ', request)
        # print('request keys: ', request.keys())
        # Id of chat
        chat_id = request['chat']['id']
        
        # If someone is deleted from the chat, delete him from the game.
        # If this bot is deleted from the chat, delete the game for this chat.
        left_participant = request.get('left_chat_participant', None)
        if left_participant:
            if left_participant['username'] == ALIAS[1:]:
                delete_all_users(chat_id)
                delete_game(chat_id)
            else:
                delete_user(chat_id, left_participant['id'])
            return
        
        game_state = get_game_state(chat_id)
        if not game_state:
            print('Game is not created. Creating')
            game_state = add_new_game(chat_id)
        
        user_id = request['from']['id']
        username = request['from']['username']
        user_state = get_user(chat_id, user_id)
        if not user_state:
            print('User is not registered. Registering')
            user_state = add_new_user(chat_id, user_id, username)
        
        process_event(request, game_state)
    except Exception:
        traceback.print_exc()
    return {'statusCode': 200}


# Parses the input from the user.
# Main logic of the game.
def process_event(request, game_state):
    state = game_state['state']
    chat = request['chat']
    chat_id = chat['id']
    user_id = request['from']['id']
    # Delete bot alias in the message
    message = request.get('text', '').replace(ALIAS,'')
    reply = request.get('reply_to_message', None)
    if message == '/restart':
        if check_if_an_admin(chat, user_id):
            delete_all_users(chat_id)
            update_game_state(chat_id, 'init')
            update_game_difficulty(chat_id, 1)
            send_message(chat_id, 'Game restarted.')
            send_categories_list(chat_id)
        return
    if message == '/help':
        send_init_message(chat_id)
        return
    if state == 'init':
        if message == '/start':
            send_init_message(chat_id)
            send_categories_list(chat_id)
            return
        elif message[0] == '/':
            set_type(chat_id, message)
        return
    labels = game_state['label']
    if state == 'checking_label':
        if 'photo' in request:
            check_user_image(chat_id, user_id, request['photo'][-1]['file_id'], labels)
        # elif 'sticker' in request:
        #     check_user_image(chat_id, user_id, request['sticker']['thumb']['file_id'], labels)
        elif message == '/set_difficulty':
            update_game_state(chat_id, 'set_difficulty')
            send_message(chat_id,
                'Choose number of concurrent labels for image searching:\n'
                '/1, /2, /3'
            )
        elif reply and message == '/report':
            if check_if_an_admin(chat, user_id):
                bad_user_id =  reply['from']['id']
                bad_user = get_user(chat_id, bad_user_id)
                update_user_score(chat_id, bad_user_id, bad_user['score']-2)
                send_message(chat_id, 
                    'Your report was accepted.\nScore of {} was decreased by 2'.format(bad_user['username']))
        elif message == '/current_score':
            user = get_user(chat_id, request['from']['id'])
            send_message(chat_id, 'Your current score is ' + str(user['score']))
        elif message == '/all_scores':
            msg = '\n'.join([
                '{}: {}'.format(u['username'], u['score'])
                for u in get_all_users(chat_id)
            ])
            send_message(chat_id, msg)
        elif message == '/current_label':
            send_message(chat_id, 'Current label(s):\n' + ' & '.join(labels))
        elif message == '/skip_label':
            if check_if_an_admin(chat, user_id):
                update_label(chat_id)
        elif message == '/change_category':
            if check_if_an_admin(chat, user_id):
                update_game_state(chat_id, 'init')
                send_categories_list(chat_id)
        elif message == '/pause':
            update_game_state(chat_id, 'paused')
            send_message(chat_id, 'Game paused.\nTo continue write /continue')
    elif state == 'set_difficulty':
        if check_if_an_admin(chat, user_id):
            if message in ['/1', '/2', '/3']:
                set_difficulty(chat_id, int(message[1]))
            else:
                send_message(chat_id, 
                    'Please, enter new difficulty! One of:\n'
                    '/1, /2, /3'
                )
        return
    elif state == 'paused':
        if message == '/continue':
            update_game_state(chat_id, 'checking_label')
            send_message(chat_id, "Let's-a go!")
            send_message(chat_id, 'Find ' + ' & '.join(labels))
    else:
        # No such state found
        send_message(chat_id, 'Wrong state: ' + game_state['state'])


# Sends init message to the chat.
def send_init_message(chat_id):
    msg = (
        '<b>Happy to see you in our "Find Me!" game bot!</b>\n\n'
        'Rules are simple: we give you a task -- you answer with a photo!\n'
        'In order to communicate with bot you may use:\n\n'
        '/start -- initiate bot for this chat for the first time\n'
        '/restart -- reset all the data and start the new game\n'
        '/pause -- make bot inactive during next messages\n'
        '/continue -- make bot active again after `/pause` was used\n'
        '/help -- show this message\n'
        '/set_difficulty -- change difficulty of the game (1-3) (only admin)\n'
        '/current_score -- your personal current score stored in bot\n'
        '/all_scores -- reveal current personal scores of each participant\n'
        '/current_label -- show again what is currently playable lable\n'
        '/skip_label -- forget current task and generate another one (only admin)\n'
        '/change_category -- choose another category from the list (only admin)\n'
        '/report -- signal about cheating, using reply (only admin)\n'
    )
    send_message(chat_id, msg)


# Sends the list of categories to the chat.
def send_categories_list(chat_id):
    msg = '\n'.join([
        'List of picture categories:',
        *['/'+ t for t in labels_dict]
    ])
    send_message(chat_id, msg)


# Registers new game in DB.
def add_new_game(chat_id):
    item = {
        'game_id': chat_id,
        'state': 'init',
        'difficulty': 1,
    }
    response = game_state_table.put_item(Item=item)
    print('add_new_game: {}'.format(response))
    return item


# Gets the game state from DB.
def get_game_state(chat_id):
    response = game_state_table.get_item(Key={'game_id': chat_id})
    return response.get('Item', None)


# Deletes specified game.
def delete_game(chat_id):
    response = game_state_table.delete_item(Key={'game_id': chat_id})
    print('delete_game: {}'.format(response))


# Updates game state in DB.
def update_game_state(chat_id, new_state):
    response = game_state_table.update_item(
        Key={'game_id': chat_id},
        UpdateExpression='SET #s = :val1',
        ExpressionAttributeValues={':val1': new_state},
        ExpressionAttributeNames={'#s': 'state'}
    )
    print('update_game_state: {}'.format(response))


# Updates game label in DB.
def update_game_label(chat_id, new_labels):
    response = game_state_table.update_item(
        Key={'game_id': chat_id},
        UpdateExpression='SET label = :val1',
        ExpressionAttributeValues={':val1': new_labels}
    )
    print('update_game_label: {}'.format(response))


# Updates game difficulty in DB.
def update_game_type(chat_id, new_type):
    response = game_state_table.update_item(
            Key={'game_id': chat_id},
            UpdateExpression='SET #t = :val1',
            ExpressionAttributeValues={':val1': new_type},
            ExpressionAttributeNames={'#t': 'type'}
    )
    print('update_game_type: {}'.format(response))


# Updates game difficulty in DB.
def update_game_difficulty(chat_id, n):
    response = game_state_table.update_item(
        Key={'game_id': chat_id},
        UpdateExpression='SET difficulty = :val1',
        ExpressionAttributeValues={':val1': n}
    )
    print('update_game_difficulty: {}'.format(response))


# Sets new difficulty.
def set_difficulty(chat_id, n):
    update_game_difficulty(chat_id, n)
    update_label(chat_id)
    print('set_difficulty')

# Adds new player to the game.
def add_new_user(chat_id, user_id, username):
    item = {
        'user_id': user_id,
        'game_id': chat_id,
        'score':0,
        'username': username
    }
    response = users_table.put_item(Item=item)
    print('add_new_user: {}'.format(response))
    return item


# Gets the shecified player in specified chat.
def get_user(chat_id, user_id):
    response = users_table.get_item(Key={
        'user_id': user_id,
        'game_id': chat_id
    })
    return response.get('Item', None)


# Gets all players of specified game.
def get_all_users(chat_id):
    response = users_table.scan(
        FilterExpression=Key('game_id').eq(chat_id)
    )
    return response.get('Items', None)


# Update score of specified player.
def update_user_score(chat_id, user_id, score):
    response = users_table.update_item(
        Key={
            'user_id': user_id,
            'game_id': chat_id
        },
        UpdateExpression='SET score = :score',
        ExpressionAttributeValues={
            ':score': score
        }
    )
    print('update_user_score: {}'.format(response))


# Delete the shecified player in specified chat.
def delete_user(chat_id, user_id):
    response = users_table.delete_item(Key={
        'user_id': user_id,
        'game_id': chat_id
    })
    print('delete_user: {}'.format(response))


# Delete all players in specified chat.
def delete_all_users(chat_id):
    users = get_all_users(chat_id)
    if users:
        transform = lambda u: {'DeleteRequest': {'Key': {
            'user_id': u['user_id'],
            'game_id': u['game_id']
        }}}
        response = database.batch_write_item(
            RequestItems={ USERS_TABLE: list(map(transform, users)) }
        )
        print('delete_all_users: {}'.format(response))
    else:
        print('No users in {}'.format(chat_id))


# Set type based on message.
def set_type(chat_id, message):
    try:
        topic_name = message[1:]
        new_type = labels_dict[topic_name]
        update_game_state(chat_id, 'checking_label')
        update_game_type(chat_id, topic_name)
        send_message(chat_id, 'Topic selected.')
        update_label(chat_id)
    except KeyError:
        send_message(chat_id, 'Please, send a valid topic')


# Update current label.
def update_label(chat_id):
    game_state = get_game_state(chat_id)
    theme_labels = labels_dict[game_state['type']]
    diff = game_state['difficulty']
    current_labels = []
    keys_list = list(labels_dict)
    if game_state['type'] == 'celebrities':
        rand_num = random.randint(0, len(theme_labels) - 1)
        current_labels.append(theme_labels[rand_num])
        for i in range(int(diff - 1)):
            rand_theme = labels_dict[keys_list[random.randint(0, len(keys_list) - 3)]]
            rand_num = random.randint(0, len(rand_theme) - 1)
            current_labels.append(rand_theme[rand_num])
    elif game_state['type'] == 'random':
        for i in range(int(diff)):
            rand_theme = labels_dict[keys_list[random.randint(0, len(keys_list) - 3)]]
            rand_num = random.randint(0, len(rand_theme) - 1)
            current_labels.append(rand_theme[rand_num])
    else:
        for i in range(int(diff)):
            rand_num = random.randint(0, len(theme_labels) - 1)
            current_labels.append(theme_labels[rand_num])
    
    update_game_state(chat_id, 'checking_label')
    update_game_label(chat_id, current_labels)
    msg = 'Find ' + ' & '.join( current_labels)
    send_message(chat_id, msg)


# Check user image, and change state.
def check_user_image(chat_id, user_id, photo_id, labels):
    image_bytes = load_photo(photo_id)
    print('Checking for {}...'.format(labels))
    try:
        response = rekognition.recognize_celebrities(Image={'Bytes': image_bytes})
        resp_labels = response['CelebrityFaces']
        response = rekognition.detect_labels(
                Image={'Bytes': image_bytes},
                MinConfidence=70.0
        )
        resp_labels += response['Labels']
        not_found = []
        for l in labels:
            if not any(label['Name'] == l for label in resp_labels):
                print(l + ' not found')
                not_found.append(l)
        if not_found:
            send_message(chat_id, '❌ {} not found'.format(' & '.join(not_found)))
        else:
            print('{} detected...'.format(labels))
            user = get_user(chat_id, user_id)
            send_message(chat_id,
                '✅, user {} got 1 point!'.format(user['username']))
            update_user_score(user['game_id'], user['user_id'], user['score']+1)
            update_label(chat_id)
    except Exception as e:
        print(e)
        print('Unable to detect labels for image.')
        raise(e)


# Loads photo from Telegram servers
# Returns object of <'bytes'>
def load_photo(photo_id):
    url1 = BASE_URL + '/getFile?file_id=' + photo_id #url to get response with file_path variable
    print('url1: ', url1)
    a = requests.get(url1)
    b = json.loads(a.text)
    file_path = b['result']['file_path']
    url2 = 'https://api.telegram.org/file/bot{}/{}'.format(TOKEN, file_path)
    image = requests.get(url2, stream=True)
    if file_path.endswith('.webp'):
        print('WEBP OCCURED: ', file_path)
        conv = Image.open(BytesIO(image.content)).convert('RGB')
        bytes_arr = BytesIO()
        conv.save(bytes_arr, format='PNG')
        return bytes_arr.getvalue()
    return image.raw.data


# Checks if given user is an admin in this chat.
# If not, send the appropriate message.
def check_if_an_admin(chat, user_id, send_msg=True):
    status = get_chat_user(chat['id'], user_id).get('status', None)
    if status:
        if status == 'creator' or status == 'administrator' or chat['type'] == 'private':
            return True
        else:
            if send_msg:
                send_message(chat_id, 'Only administrators can make such requests')
            return False
    else:
        print('User with id: {} not found in chat {}'.format(user_id, chat_id))


# Gets the data about specified user from DB.
def get_chat_user(chat_id, user_id):
    request = {'chat_id': chat_id, 'user_id': user_id}
    url = BASE_URL + '/getChatMember'
    response = requests.post(url, request)
    print(response.json())
    print(type(response.json()))
    return response.json()['result']


# Sends message to the specified chat.
def send_message(chat_id, msg):
    request = {'text': msg.encode('utf8'), 'chat_id': chat_id, 'parse_mode':'HTML'}
    url = BASE_URL + '/sendMessage'
    print('Sended message:' + msg)
    requests.post(url, request)
