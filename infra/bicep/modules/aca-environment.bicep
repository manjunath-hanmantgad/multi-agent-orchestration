param location string
param environmentName string
param logAnalyticsWorkspaceId string
param logAnalyticsSharedKey string

resource acaEnv 'Microsoft.App/managedEnvironments@2023-11-02-preview' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspaceId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

output id string = acaEnv.id
output name string = acaEnv.name
