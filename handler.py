import json
import os
import sys
import boto3
import random
here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "./vendored"))

import requests



# Gain from evnironment of server
TOKEN = os.environ['TELEGRAM_TOKEN']
BASE_URL = "https://api.telegram.org/bot{}".format(TOKEN)

SUPPORTED_TYPES = ['image/jpeg', 'image/jpg', 'image/png']  # Supported image types
MAX_SIZE = 5242880  # Max number of image bytes supported by Amazon Rekognition (5MiB)

rekognition = boto3.client('rekognition') # Rekognition client

# Database tables
database = boto3.resource('dynamodb', region_name='eu-west-1')
game_state_table = database.Table('game_state')
users_table = database.Table('users')


# Categories that players can pick
topics = ["/animal", "/nature", "/ancient_epoch_weapons"]

labels_dict = {
    'People and Events': ['Wedding', 'Bride', 'Baby', 'Birthday Cake', 'Guitarist'],
    'Food and Drink': ['Apple', 'Sandwich', 'Wine', 'Cake', 'Pizza'],
    'Nature and Outdoors': ['Beach', 'Mountains', 'Lake', 'Sunset', 'Rainbow'],
    'Animals and Pets': ['Dog', 'Cat', 'Horse', 'Tiger', 'Turtle'],
    'Home and Garden': ['Bed', 'Table', 'Backyard', 'Chandelier', 'Bedroom'],
    'Sports and Leisure': ['Golf', 'Basketball', 'Hockey', 'Tennis', 'Hiking'],
    'Plants and Flowers': ['Rose', 'Tulip', 'Palm Tree', 'Forest', 'Bamboo'],
    'Art and Entertainment': ['Sculpture', 'Painting', 'Guitar', 'Ballet', 'Mosaic'],
    'Transportation and Vehicles': ['Airplane', 'Car', 'Bicycle', 'Motorcycle', 'Truck'],
    'Electronics': ['Computer', 'Mobile Phone', 'Video Camera', 'TV', 'Headphones']
}


# Lambda entry funciton. event - object from Telegram server
def hello(event, context):
    try:
        request = json.loads(event["body"])["message"]
        # Just for debug
        print("request: ", request)
        print("request keys: ", request.keys())
        # Way to pick id of chat
        chat_id = request["chat"]["id"]
        # XXX: message that user sent (contains other important information)
        message = str(request.get('text', ''))
        # This variable will be sent to user
        response = "Please /start"
        
        game_state = get_game_state(chat_id)
        if not game_state:
            # TODO: Check if works
            send_message(chat_id, "Game is not created. Creating")
            print("Game is not created. Creating")
            game_state = add_new_game(chat_id)
        
        user_id = request['from']['id']
        username = request['from']['username']
        user_state = get_user(chat_id, user_id)
        if not user_state:
            # TODO: Check if works
            send_message(chat_id, "User is not registered. Registering")
            print("User is not registered. Registering")
            user_state = add_new_user(chat_id, user_id, username)
        
        process_event(request, game_state)
        # # User's input parsing
        # # User sent photo
        # if "photo" in request:
            # print("Photo was sent.")
            # response = recognize_photo(request)
        # else:
            # # /start command
            # if "/start" in message:
                # response = get_topics_msg()
            # # topic selected
            # if message in topics:
                # response = "Your next aim is: ..." + get_next_aim(request)
        # # Just for debug
        # print("Response: ", response)
        # send_message(chat_id, response)
    except Exception as e:
        print(e)
    return {"statusCode": 200}

def process_event(request, game_state):
    state = game_state['state']
    chat_id = request['chat']['id']
    message = request['text']
    if state == 'init':
        if message == '/start':
            msg = '\n'.join([
                "Hello, guys, it's, Johan. Here are my labels:",
                *[t for t in labels_dict.keys()]
            ])
            send_message(chat_id, msg)
            return
        set_type(chat_id, message)
        return
    if state == 'checking_label':
        if "photo" in request:
            check_user_image(request, labels_dict[game_state['type']][game_state['label']])
        elif message == '/restart_game':
            set_new_state(chat_id, 'init')
            send_message(chat_id, 'Game restarted.')
        elif message == '/current_score':
            user = get_user(chat_id, event_details['user'])
            send_message(chat_id, 'Your current score is ' + user['score'])
            return
        elif message == '/all_scores':
            msg = '\n'.join([
                '{}: {}'.format(u['username'], u['score'])
                for u in get_all_users(chat_id)
            ])
            send_message(chat_id, msg)
            return
        elif message != '':
            send_message(chat_id, 'Wrong message')
        return
    # No such state found
    send_message(chat_id, 'Wrong state: ' + game_state['state'])


def add_new_game(chat_id):
    item = {
        'game_id': chat_id,
        'state': 'init'
    }
    response = game_state_table.put_item(Item=item)
    print('add_new_game: {}'.format(response))
    return item
    


def get_game_state(chat_id):
    response = game_state_table.get_item(Key={'game_id': chat_id})
    return response.get('Item', None)


def update_game_state(chat_id, new_state):
    response = game_state_table.update_item(
            Key={'game_id': chat_id},
            UpdateExpression='SET #s = :val1',
            ExpressionAttributeValues={':val1': new_state},
            ExpressionAttributeNames={'#s': 'state'}
        )
    print('update_game_state: {}'.format(response))


def update_game_label(chat_id, new_label):
    response = game_state_table.update_item(
        Key={'game_id': chat_id},
        UpdateExpression='SET label = :val1',
        ExpressionAttributeValues={':val1': new_label}
    )
    print('update_game_label: {}'.format(response))


def update_game_type(chat_id, new_type):
    response = game_state_table.update_item(
            Key={'game_id': chat_id},
            UpdateExpression='SET #t = :val1',
            ExpressionAttributeValues={':val1': new_type},
            ExpressionAttributeNames={'#t': 'type'}
    )
    print('update_game_type: {}'.format(response))


def add_new_user(chat_id, user_id, username):
    item = {
        'user_id': user_id,
        'game_id': game_id,
        'score':0,
        'username': username
    }
    response = users_table.put_item(Item=item)
    print('add_new_user: {}'.format(response))
    return item


def get_user(chat_id, user_id):
    response = users_table.get_item(Key={
        'user_id': user_id,
        'game_id': chat_id
    })
    return response.get('Item', None)


def get_all_users(chat_id):
    response = users_table.scan(
        FilterExpression=Key('game_id').eq(chat_id)
    )
    return response.get('Items', None)


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


def set_type(chat_id, message):
    try:
        type_num = int(message)
        if type_num < 0 or type_num > len(labels_dict):
            send_message(chat_id, 'Please, send a valid number.')
        else:
            send_message(chat_id, "set_type")
            new_type = labels_dict.keys()[type_num]
            update_game_state(chat_id, 'checking_label')
            update_game_type(chat_id, new_type)
            update_label(chat_id)
    except ValueError:
        send_message(chat_id, 'Please, send a number.')


def update_label(chat_id):
    game_state = get_game_state(chat_id)
    theme_labels = labels_dict[game_state['type']]
    current_label = random.randint(0, len(theme_labels))
    update_game_state(chat_id, 'checking_label')
    update_game_label(chat_id, current_label)
    send_message(chat_id, 'Current theme: {}'.format(theme))
    send_message(chat_id, 'Find {}'.format(theme_labels[current_label]))


def check_user_image(request, label_name):
    chat_id = request['chat']['id']
    if check_label(request, label_name):
        user_id = request['from']['id']
        user = get_user(chat_id, user_id)
        send_message(chat_id, 
            '{} ✅, user {} got 1 point!'.format(label_name, user['username']))
        set_user_score(user['game_id'], user['user_id'], user['score']+1)
        update_label(chat_id)
    else:
        send_message(chat_id,
            'Not {} ❌'.format(label_name))


def check_label(request, label_name):
    image_bytes = load_photo(request)
    print('Checking for {}...'.format(label_name))
    has_label = detect_label(image_bytes, label_name)
    if has_label:
        print('{} detected...'.format(label_name))
        return True
    else:
        print('{} not detected...'.format(label_name))
        return False


def recognize_photo(photo):
    #Recognize photo
    try:
        response = rekognition.detect_labels(
            Image={'Bytes': photo},
            MinConfidence=80.0
        )
    except Exception as e:
        print(e)
        print('Unable to detect labels for image.')
        raise(e)
    labels = response['Labels']
    if any(label['Name'] == label_name for label in labels):
        return True
    return False

# Function returns object of <'bytes'>
def load_photo(request):
    url1 = BASE_URL + "/getFile?file_id={}".format(request["photo"][-1]["file_id"]) #url to get response with file_path variable
    print("url1: ", url1)
    a = requests.get(url1)
    b = json.loads(a.text)
    file_path = b['result']['file_path']
    url2 = "https://api.telegram.org/file/bot{}/{}".format(TOKEN, file_path)
    image = requests.get(url2, stream=True)
    return image.raw.data


def get_topics_msg():
    return "Select topic:\n" + "\n".join(topics)


def send_message(chat_id, msg):
    request = {"text": msg.encode("utf8"), "chat_id": chat_id}
    url = BASE_URL + "/sendMessage"
    requests.post(url, request)
