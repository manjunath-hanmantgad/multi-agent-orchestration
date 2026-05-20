param location string
param serverName string
param adminUser string = 'observatoryadmin'
@secure()
param adminPassword string
param skuName string = 'Standard_B1ms'
param tier string = 'Burstable'
param storageSizeGB int = 32
param postgresVersion string = '16'

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: serverName
  location: location
  sku: {
    name: skuName
    tier: tier
  }
  properties: {
    administratorLogin: adminUser
    administratorLoginPassword: adminPassword
    version: postgresVersion
    storage: {
      storageSizeGB: storageSizeGB
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: postgres
  name: 'maw'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

output fqdn string = postgres.properties.fullyQualifiedDomainName
output databaseName string = database.name
