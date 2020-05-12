from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Dial, Gather
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


app = Flask(__name__)
app.config.from_object('settings')

client = Client(
    app.config['TWILIO_ACCOUNT_SID'],
    app.config['TWILIO_AUTH_TOKEN'])

VERIFY_SERVICE_SID = app.config['VERIFY_SERVICE_SID']
MODERATOR = app.config['MODERATOR']
KNOWN_PARTICIPANTS = app.config['KNOWN_PARTICIPANTS']


def start_verification(caller):
    # don't send another code if there's already a pending verification
    try:
        client.verify \
            .services(VERIFY_SERVICE_SID) \
            .verifications(caller) \
            .fetch()
    except TwilioRestException as e:
        print("No pending verifications for {}".format(caller))

        # verify the user is not spoofing a phone number
        # alternative: could look up a participant's email 
        # and send a code via email: twilio.com/docs/verify/email
        client.verify \
            .services(VERIFY_SERVICE_SID) \
            .verifications \
            .create(to=caller, channel='sms')


def check_verification(caller, otp):
    check = client.verify \
        .services(VERIFY_SERVICE_SID) \
        .verification_checks \
        .create(to=caller, code=otp)
    
    return check.status == 'approved'


def join_conference(caller, resp):
   with Dial() as dial:
       # If the caller is our MODERATOR, then start the conference when they
       # join and end the conference when they leave
       if request.values.get('From') == MODERATOR:
           dial.conference(
               'My conference',
               start_conference_on_enter=True,
               end_conference_on_exit=True)
       else:
           # Otherwise have the caller join as a regular participant
           dial.conference('My conference', start_conference_on_enter=False)
      
       resp.append(dial)
       return str(resp)


@app.route("/voice", methods=['GET', 'POST'])
def voice():
    """Respond to incoming phone calls with a menu of options"""
    # Start our TwiML response
    resp = VoiceResponse()
    caller = request.values.get('From')

    # verify the phone number has access to the call
    name = KNOWN_PARTICIPANTS.get(caller)
    if name is None:
        resp.say("Sorry, I don't recognize the number you're calling from.")
        return str(resp)
    
    start_verification(caller)

    # Start our <Gather> verb
    gather = Gather(num_digits=6, action='/gather')
    gather.say(
        "Welcome {}. Please enter the 6 digit code sent to your device.".format(
            name))
    resp.append(gather)

    # If the user doesn't select an option, redirect them into a loop
    resp.redirect('/voice')

    return str(resp)


@app.route('/gather', methods=['GET', 'POST'])
def gather():
    """Processes results from the <Gather> prompt in /voice"""
    # Start our TwiML response
    resp = VoiceResponse()

    # If Twilio's request to our app included already gathered digits,
    # process them
    if 'Digits' in request.values:
        # Get the one-time password input
        caller = request.values['From']

        if check_verification(caller, request.values['Digits']):
            resp.say("That was correct. Joining conference.")
            return join_conference(caller, resp)
        else:
            resp.say("Please try again.")
            resp.redirect('/voice')

    return str(resp)
