from nova_act import NovaAct
import boto3

def get_nova_api_key():
    secret_name = "nova-api-key"
    region_name = "eu-central-1"
    
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        return get_secret_value_response['SecretString']
    except Exception as e:
        print(f"Error retrieving API key: {e}")
        return None



# Get API key from Secrets Manager
nova_api_key = get_nova_api_key()

with NovaAct(starting_page="https://www.zalando.de", nova_act_api_key=nova_api_key, logs_directory='logs') as nova:
    # nova.act("You are a UX researcher based on your experience do you see the landingpage follows UX best practices for example but not limited to: 1. Banner blindnes, 2. Contrasts, 3. Clear navigation 4. Finding the right product")
    result = nova.act("You are a helpful UX research expert helping me to research a new user flow. The flow is as follows: 'I am a man looking to buy a new adidas shorts' can you help me to navigate the page and find adidas shorts for men", model_temperature=1)
    print("steps taken: ", result.metadata.num_steps_executed)
    print("duration: ", result.metadata.end_time - result.metadata.start_time)
