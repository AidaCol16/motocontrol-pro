import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

async def consultar_impresora(ip):
    # OIDs estándar (Printer MIB)
    oid_contador = '1.3.6.1.2.1.43.10.2.1.4.1.1'
    oid_toner_max = '1.3.6.1.2.1.43.11.1.1.8.1.1'
    oid_toner_actual = '1.3.6.1.2.1.43.11.1.1.9.1.1'

    snmp_engine = SnmpEngine()

    async def get_snmp_value(oid):
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmp_engine,
            CommunityData('public', mpModel=0),
            # Aquí está el cambio clave de la versión 7:
            await UdpTransportTarget.create((ip, 161)), 
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        
        if errorIndication:
            print(f"[!] Error de red o SNMP inactivo: {errorIndication}")
            return None
        elif errorStatus:
            print(f"[!] Error SNMP: {errorStatus.prettyPrint()}")
            return None
            
        return int(varBinds[0][1])

    print(f"[*] Conectando a la impresora en {ip}...\n")

    # 1. Obtener cantidad de impresiones
    paginas = await get_snmp_value(oid_contador)

    # 2. Obtener datos del Tóner
    capacidad_maxima = await get_snmp_value(oid_toner_max)
    nivel_actual = await get_snmp_value(oid_toner_actual)

    # 3. Calcular porcentaje y alertas
    porcentaje_toner = 0
    alerta_agotado = False

    if capacidad_maxima is not None and nivel_actual is not None:
        if nivel_actual >= 0 and capacidad_maxima > 0:
            porcentaje_toner = round((nivel_actual / capacidad_maxima) * 100)
        
        if porcentaje_toner <= 5:
            alerta_agotado = True

    return {
        "impresiones": paginas,
        "porcentaje_toner": porcentaje_toner,
        "alerta_agotado": alerta_agotado
    }

if __name__ == "__main__":
    ip_impresora = '192.168.3.115'
    
    datos = asyncio.run(consultar_impresora(ip_impresora))
    
    if datos["impresiones"] is not None:
        print("-" * 30)
        print(f"Total Impresiones: {datos['impresiones']} páginas")
        print(f"Nivel de Tóner:    {datos['porcentaje_toner']}%")
        print("-" * 30)
        
        if datos['alerta_agotado']:
            print(">>> ¡ALERTA!: El tóner se está agotando. <<<")
    else:
        print("\n[!] No se pudo conectar. Verifica que la IP sea correcta y el protocolo SNMP esté activo en la impresora.")