import json
import os
import sys
here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "./vendored"))

import requests


# Gain from evnironment of server
TOKEN = os.environ['TELEGRAM_TOKEN']
BASE_URL = "https://api.telegram.org/bot{}".format(TOKEN)


# Categories that players can pick
topics = ["/animal", "/nature", "/ancient_epoch_weapons"]


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
        message = str(request["text"]) if "text" in request else ""
        # first_name = request["chat"]["first_name"]
        # This variable will be sent to user
        response = "Please /start"

        # User's input parsing
        # User sent photo
        if "photo" in request:
            print("Photo was sent.")
            response = recognize_photo(request)
        else:
            # /start command
            if "/start" in message:
                response = get_topics_msg()
            # topic selected
            if message in topics:
                response = "Your next aim is: ..." + get_next_aim(request)
        # Just for debug
        print("Response: ", response)
        send_message(response, chat_id)
    except Exception as e:
        print(e)
    return {"statusCode": 200}


def get_score():
    pass


# Do we need this function?
def restart_game():
    pass 


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


def recognize_photo(request):
    #Check game state

    #Load photo
    photo = load_photo(request) #Function returns object of <'bytes'>
    print(type(photo))
    print(dir(photo))
    #Recognize photo

    #Update state

    #Return result
    return "Photo recognized!"


def get_next_aim(request):
    #Randomly select next object to recognize

    #Update room state in BD

    #Return next object name
    return "Shiny kitty :3"


def get_topics_msg():
    return "Select topic:\n" + "\n".join(topics)


def send_message(msg, chat_id):
    request = {"text": msg.encode("utf8"), "chat_id": chat_id}
    url = BASE_URL + "/sendMessage"
    requests.post(url, request)
