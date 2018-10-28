import os
import random
import urllib
import boto3

SUPPORTED_TYPES = ['image/jpeg', 'image/jpg', 'image/png']  # Supported image types
MAX_SIZE = 5242880  # Max number of image bytes supported by Amazon Rekognition (5MiB)

VERIFICATION_TOKEN = os.environ['VERIFICATION_TOKEN']  # Slack verification token from environment variables
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']  # Slack OAuth access token from environment variables

rekognition = boto3.client('rekognition')

database = boto3.resource('dynamodb', region_name='eu-west-1')
game_state_table = database.Table('game_state')
users_table = database.Table('users')

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


def lambda_handler(event, context):
    print('Validating message...')
    print(event)
    print(context)
    if not verify_token(event):  # Ignore event if verification token presented doesn't match
        return
    if event['event'].get('subtype') == 'bot_message': # Ignore bot messages
        print('Bot message, skip')
        return
    if event.get('challenge') is not None:  # Respond to Slack event subscription URL verification challenge
        print('Presented with URL verification challenge- responding accordingly...')
        challenge = event['challenge']
        return {'challenge': challenge}
    
    print('Getting state')
    game_state = get_game_state(event)
    print(game_state)
    
    channel = event['event'].get('channel')
    
    if game_state == None:
        post_message(channel, 'Game is not created')
        # TODO: create_game
    if parse_messages(event, game_state): #If current message needs to stop this lambda, stop
        return
    game_state = get_game_state(event) # TODO: get the new state from `parse_messages`
    state = game_state['state']
    if state == 'init':
        set_label(event)
    elif state == 'checking_label':
        check_label(event, game_state['label'])
    else:
        post_message(channel, "Wrong state: {}".format(state))

def parse_messages(event, game_state):
    event_details = event['event']
    channel = event_details.get('channel')
    message = event_details.get('text')
    if message == 'restart_bot':
        set_game_state(channel, 'init')
        post_message(channel, "Game restarted.")
        return False
    elif message == 'current_score':
        user = get_user(event_details['channel'], event_details['user'])
        post_message(channel, "Your current score is {}".format(user['score']))
        return False
    elif message == '':
        return False
    else:
        post_message(channel, "Find {}".format(game_state['label']))
        return False

def get_game_state(event):
    result = game_state_table.get_item(
        Key={
            'game_id': event['event'].get('channel')
        })
    return result['Item']

def set_game_state(game_id, new_state, new_label=None):
    key = {
        'game_id': game_id
    }
    expr_attr_names = {
        '#s': 'state'
    }
    upd_expr = ''
    expr_attr_vals = {}
    if new_label != None:
        upd_expr='SET #s = :val1, label = :val2'
        expr_attr_vals={
            ':val1': new_state,
            ':val2': new_label
        }
    else:
        upd_expr='SET #s = :val1'
        expr_attr_vals={
            ':val1': new_state
        }
    result = game_state_table.update_item(
            Key=key,
            UpdateExpression=upd_expr,
            ExpressionAttributeValues=expr_attr_vals,
            ExpressionAttributeNames=expr_attr_names
        )
    print('set_game_state: {}'.format(result))

def get_user(game_id, user_id):
    result = users_table.get_item(
        Key={
            'user_id': user_id,
            'game_id': game_id
        })
    return result['Item']

def set_user_score(game_id, user_id, score):
    print(game_id, user_id, score)
    result = users_table.update_item(
            Key={
                'user_id': user_id,
                'game_id': game_id
            },
            UpdateExpression='SET score = :score',
            ExpressionAttributeValues={
                ':score': score
            }
        )
    print('set_user_score: {}'.format(result))


def set_label(event, theme = 'Animals and Pets'):
    channel = event['event'].get('channel')
    theme_labels = labels_dict['Animals and Pets']
    current_label = theme_labels[random.randint(0,len(theme_labels))]
    set_game_state(channel, 'checking_label', current_label)
    post_message(channel, 'Current theme: {}'.format(theme))
    post_message(channel, 'Find {}'.format(current_label))


def check_label(event, label_name):
    if not validate_event(event):  # Ignore event if Slack message doesn't contain any supported images
        post_message(event['event'].get('channel'), 'Please, send an image with {}'.format(label_name))
        return
    event_details = event['event']
    
    user = get_user(event_details['channel'], event_details['user'])
    
    file_details = event_details['files'][0]
    
    channel = event_details['channel']
    url = file_details['url_private']
    file_id = file_details['id']
    
    print('Downloading image...')
    image_bytes = download_image(url)
    print('Checking for {}...'.format(label_name))
    is_hotdog = detect_label(image_bytes, label_name)
    message = ""
    if is_hotdog:
        print('{} detected...'.format(label_name))
        message = '{} ✅, user {} got 1 point!'.format(label_name, user['user_id'])
        set_user_score(user['game_id'], user['user_id'], user['score']+1)
    else:
        print('{} not detected...'.format(label_name))
        message = 'Not {} ❌, user {} lose 1 point!'.format(label_name, user['user_id'])
        set_user_score(user['game_id'], user['user_id'], user['score']-1)
    post_message(channel, message)


def verify_token(event):
    """ Verifies token presented in incoming event message matches the token copied when creating Slack app.

    Args:
        event (dict): Details about incoming event message, including verification token.

    Returns:
        (boolean)
        True if presented with the valid token.
        False otherwise.

    """
    if event['token'] != VERIFICATION_TOKEN:
        print('Presented with invalid token- ignoring message...')
        return False
    return True


def validate_event(event):
    """ Validates event by checking contained Slack message for image of supported type and size.

    Args:
        event (dict): Details about Slack message and any attachements.

    Returns:
        (boolean)
        True if event contains Slack message with supported image size and type.
        False otherwise.
    """
    event_details = event['event']
    file_subtype = event_details.get('subtype')

    if file_subtype != 'file_share':
        print('Not a file_shared event- ignoring event...')
        return False

    file_details = event_details['files'][0]
    mime_type = file_details['mimetype']
    file_size = file_details['size']

    if mime_type not in SUPPORTED_TYPES:
        print('File is not an image- ignoring event...')
        return False

    if file_size > MAX_SIZE:
        print('Image is larger than 5MB and cannot be processed- ignoring event...')
        return False

    return True


def download_image(url):
    """ Download image from private Slack URL using bearer token authorization.

    Args:
        url (string): Private Slack URL for uploaded image.

    Returns:
        (bytes)
        Blob of bytes for downloaded image.


    """
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer %s' % ACCESS_TOKEN})
    return urllib.request.urlopen(request).read()


def detect_label(image_bytes, label_name):
    """ Checks image for hotdog label using Amazon Rekoginition's object and scene detection deep learning feature.

    Args:
        image_bytes (bytes): Blob of image bytes.

    Returns:
        (boolean)
        True if object and scene detection finds hotdog in blob of image bytes.
        False otherwise.

    """
    try:
        response = rekognition.detect_labels(
            Image={
                'Bytes': image_bytes,
            },
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


def post_message(channel, message):
    """ Posts message to Slack channel via Slack API.

    Args:
        channel (string): Channel, private group, or IM channel to send message to. Can be an encoded ID, or a name.
        message (string): Message to post to channel

    Returns:
        (None)
    """
    url = 'https://slack.com/api/chat.postMessage'
    data = urllib.parse.urlencode(
        (
            ("token", ACCESS_TOKEN),
            ("channel", channel),
            ("text", message)
        )
    )
    data = data.encode("ascii")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    request = urllib.request.Request(url, data, headers)
    urllib.request.urlopen(request)
