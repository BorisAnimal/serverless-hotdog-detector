To deploy:

after init.sh, you could use 
$ serverless deploy	 #in folder with handler.py and serverless.yml

Then you will receive output with text like:
... https://api.telegram.org/bot<Your Telegram TOKEN>/setWebhook ...

go to your terminal again and execute this line (put your url and TOKEN):
$ curl --request POST --url https://api.telegram.org/botAPHruyw7ZFj5qOJmJGeYEmfFJxil-z5uLS8/setWebhook --header 'content-type: application/json' --data '{"url": "https://u3ir5tjcsf.execute-api.us-east-1.amazonaws.com/dev/secret-hook-for-telegram"}'

Don't forget to customize your curl content!
