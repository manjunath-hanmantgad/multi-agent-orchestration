param location string
param appName string
param environmentId string
param imageName string
param containerPort int = 8001
param minReplicas int = 0
param maxReplicas int = 3
param env array = []
param secrets array = []
param command array = []

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${appName}-identity'
  location: location
}

resource app 'Microsoft.App/containerApps@2023-11-02-preview' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: containerPort > 0 ? {
        external: true
        targetPort: containerPort
        transport: 'http'
      } : null
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: appName
          image: imageName
          command: command
          env: env
          resources: {
            cpu: 1
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output fqdn string = containerPort > 0 ? app.properties.configuration.ingress.fqdn : ''
output principalId string = identity.properties.principalId
output identityId string = identity.id
