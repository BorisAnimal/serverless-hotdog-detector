# "Find something" - game in a messenger.
Simple game for the Slack messenger, using the AWS services for the image recognition, storage and logic for the bot.\
The project is based on the [Serverless-HotDog-Detector](https://github.com/aws-samples/serverless-hotdog-detector).
#### Authors:
Maxim Surkov\
Boris Guryev\
Denis Chernikov\
Vladislav Kuleykin

## Purpose
This project was created during the *Distributed Systems and Cloud Computing* course at *Fall 2018* at *Innopolis University*.

## How to run
TODO

### Game Rules
The Game is played by a group of people in a messenger group chat.

When game decides to start a new competition it writes "Game Starts Now" and announces object that should be found. Each player has score and he receives points when sends a photo of required object to chat.

There are several game types:
1) Find single object
2) Find several objects in one photo
3) Find some object given indirect description

### Implementation Details
Game Logic is deployed as an AWS Lambda function. Competition state is stored through integration with AWS DynamoDB and attached to the Lambda. The Game Logic is independent from user interface handler and thus would be accessible either through Slack chat or through third-party extension like Telegram Bot as well.

### HLD
![](images/Architecture.png)
