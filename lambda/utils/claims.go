package utils

import (
	"github.com/aws/aws-lambda-go/events"
	"github.com/mitchellh/mapstructure"
)

type Claims struct {
	Email string
	Sub   string
}

func DecodeClaims(r events.APIGatewayProxyRequest) (Claims, error) {
	input := r.RequestContext.Authorizer["claims"]
	output := Claims{}
	err := mapstructure.Decode(input, &output)

	if err != nil {
		return Claims{}, err
	}

	return output, nil
}
