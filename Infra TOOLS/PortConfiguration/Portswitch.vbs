'--------------------------------------------------------------------
' Portswitch.vbs
' Usage: Portswitch (HTTP port number)
' Example:Portswitch 1337
' (c) Microsoft Corporation. All rights reserved.
'
' This script will set the HTTP port on which the
' ConfigMgr Advanced Client will use to communicate with the Management Point.
' This script is intended to be used with software distribution.
' Because file associations can change it is recommended that you execute portswitch.vbs in the
' following way:
'
' The command line provided in the package's program should be "wscript.exe portswitch.vbs
' (HTTP port number) (optional: HTTPS port number)"
'
' Example: "Wscript.exe portswitch.vbs 1337 31337"
'
'
' To properly generate pass/fail status for software distribution you must do the following:
' 1) In the ConfigMgr package, set the MIF matching properties to the following:
'      MIF Filename:  "Portswitch.mif"
' 2) In the ConfigMgr Program, you must specify that the "Program will reboot"
'      (this is because CCMExec restarts)
'
'--------------------------------------------------------------------

Dim objShell 'This establishes the variable Shell that will become the WScript.Shell object.
Dim nPortValue, nSslPortValue, nReadValue 'Holds the value passed as a command argument
Dim CCMService

Const EVENT_SUCESS = 0
Const EVENT_FAILED = 2

Const Reg_PortKey = "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\CCM\HttpPort" 'Set constant as the registry path to the desired key.
Const Reg_PortKeySSL = "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\CCM\HttpsPort" 'SSL port for ConfigMgr client

' Create a WScript.Shell oject
Set objShell = Wscript.CreateObject("Wscript.Shell")

' check the argument count
iNumberOfArguments = Wscript.Arguments.Count
If iNumberOfArguments > 2 or iNumberOfArguments < 1 Then
    objShell.LogEvent EVENT_FAILED, _
            "Portswitch.vbs was executed with no specified port. " & _
            "Usage: Portswitch (HTTP port number) " & _
            "(optional HTTPS port number). Examples: ""Portswitch 8080"" or ""PortSwitch 8080 8443""" 
    FailAndQuit
End if

On Error Resume Next
' Validate the port arguments, and set the ports in the registry
nPortValue = CLng(Wscript.Arguments.Item(0))
ValidatePort nPortValue

' If we have an SSL port, validate it, too.
If iNumberOfArguments = 2 Then
    nSslPortValue = CLng(Wscript.Arguments.Item(1))
    If nSslPortValue = nPortValue Then
        objShell.LogEvent EVENT_FAILED, _
            "Portswitch.vbs had an invalid port specification: HTTP and HTTPS ports cannot be identical."
        FailAndQuit
    End If

    ValidatePort nSslPortValue
    WriteRegKey Reg_PortKeySSL, nSslPortValue
End If

WriteRegKey Reg_PortKey, nPortValue

Set objWmiservice = GetObject("winmgmts:root\cimv2:Win32_Service.Name=""CCMExec""")

' Stop the CCMExec so the port change may be picked up by the client.
errReturnCode = objWMIService.StopService()

If errReturnCode <> 0 Then
    objShell.LogEvent EVENT_FAILED, _
        "Portswitch.vbs was unable to stop the CCMExec service: (Err=" & errReturnCode & ")"
    FailAndQuit
End If

' Wait for the ccmexec service to stop  (to a maximum of 10 minutes)
Dim dWaitUntil
dWaitUntil = DateAdd("n", 10, Now)
Do While (objWMIService.InterrogateService() <> 6) And (Now < dWaitUntil)
    ' The service is still running
    WScript.Sleep 1000
Loop

' Did the service stop?
If objWMIService.InterrogateService() <> 6 then
    objShell.LogEvent EVENT_FAILED, _
        "Portswitch.vbs timed out trying to stop the CCMExec service after 3 minutes."
    FailAndQuit
End If

If Err.number <> 0 Then
    objShell.LogEvent EVENT_FAILED, _
    "Portswitch.vbs - An error occured: " & Err.Description
    FailAndQuit
End If

' Generate a success status mif
WriteStatusMIF(true)

' Starting CCMExec so the port change may be picked up by the client.
errReturnCode = objWMIService.StartService ()
If iNumberOfArguments = 2 Then
    objShell.LogEvent EVENT_SUCCESS, _
        "The ConfigMgr Advanced Client has been successfully set to communicate with the MP on ports " & nPortValue & " (HTTP) and " & nSslPortValue & " (HTTPS)"
Else
    objShell.LogEvent EVENT_SUCCESS, _
        "The ConfigMgr Advanced Client has been successfully set to communicate with the MP on port " & nPortValue
End If

WScript.Quit(0)
' -----------------------------

ErrorHandler:
    objShell.LogEvent EVENT_FAILED, _
        "Portswitch failed with an internal error: " & Err.Description
    FailAndQuit

' -----------------------------
Sub ValidatePort(nPort)
    If Err.number <> 0 Then
        objShell.LogEvent EVENT_FAILED, _
            "Portswitch.vbs - An invalid port number was specified  (Valid ports are 1-65535). " & _
            "Usage: Portswitch (HTTP port number) Example: Portswitch 8080"
        FailAndQuit
    End If

    ' Check the port value
    If nPort  < 1 or nPort > 65535 then
        objShell.LogEvent EVENT_FAILED, _
            "Portswitch.vbs was executed with an invalid port number (" & nPort & "). Port numbers must fall " & _
            "between 1-65535 Usage: Portswitch (HTTP port number) Example: Portswitch 8080"
        FailAndQuit
    End if
End Sub

' -----------------------------
Sub WriteRegKey(sRegKey, nPort)
    nReadValue = objShell.RegRead(sRegKey)
    If nReadValue then
        ' Write current path to registry key and read it to become constant for script.
        objShell.RegWrite (sRegKey), nPort, "REG_DWORD"
        nReadValue = objShell.RegRead(sRegKey)
    else
        objShell.LogEvent EVENT_FAILED, _
            "Portswitch is unable to modify the Registry. The Registry Key is not present. This must be an RTM Advanced Client or a Legacy Client."
        FailAndQuit
    End If
End Sub

' -----------------------------
Sub FailAndQuit()
    WriteStatusMIF(false)
    WScript.Quit(1)
End Sub


' -----------------------------
Sub WriteStatusMIF(bSuccess)

    ' Writing a status MIF for SWDist to return a success or a failure to execute
    Const ForWriting = 2
    Const TemporaryFolder = 2
    Set objFSO = CreateObject("Scripting.FileSystemObject")
    Dim strTempDir
    strTempDir = objFSO.GetSpecialFolder(TemporaryFolder)
    Set objFile = objFSO.CreateTextFile(strTempDir & "\portswitch.mif", ForWriting)
    objFile.Writeline ("START COMPONENT")
    objFile.Writeline ("NAME = ""WORKSTATION""")
    objFile.Writeline ("  START GROUP")
    objFile.Writeline ("    NAME = ""ComponentID""")
    objFile.Writeline ("    ID = 1")
    objFile.Writeline ("    CLASS = ""DMTF|ComponentID|1.0""")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Manufacturer""")
    objFile.Writeline ("      ID = 1")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(64)")
    objFile.Writeline ("      VALUE = ""Microsoft""")
    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Product""")
    objFile.Writeline ("      ID = 2")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(64)")
    objFile.Writeline ("      VALUE = ""Portswitch""")
    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Version""")
    objFile.Writeline ("      ID = 3")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(64)")
    objFile.Writeline ("      VALUE = ""1.0""")
    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Locale""")
    objFile.Writeline ("      ID = 4")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(16)")
    objFile.Writeline ("      VALUE = ""ENU""")
    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Serial Number""")
    objFile.Writeline ("      ID = 5")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(64)")
    objFile.Writeline ("      VALUE = """"")
    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Installation""")
    objFile.Writeline ("      ID = 6")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(64)")
    objFile.Writeline ("      VALUE = ""DateTime""")
    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("  END GROUP")
    objFile.Writeline ("  START GROUP")
    objFile.Writeline ("    NAME = ""InstallStatus""")
    objFile.Writeline ("    ID = 2")
    objFile.Writeline ("    CLASS = ""MICROSOFT|JOBSTATUS|1.0""")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Status""")
    objFile.Writeline ("      ID = 1")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(32)")

    ' Pass or fail this status mif?
    If bSuccess = true then
        objFile.Writeline ("      VALUE = ""Success""")
    else
        objFile.Writeline ("      VALUE = ""Failed""")
    End if

    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("    START ATTRIBUTE")
    objFile.Writeline ("      NAME = ""Description""")
    objFile.Writeline ("      ID = 2")
    objFile.Writeline ("      ACCESS = READ-ONLY")
    objFile.Writeline ("      STORAGE = SPECIFIC")
    objFile.Writeline ("      TYPE = STRING(128)")

    If bSuccess = true and iNumberOfArguments = 2 then
        objFile.Writeline ("      VALUE = ""The ConfigMgr Advanced Client has been successfully set to communicate with the MP on ports " & nPortValue & " (HTTP) and " & nSslPortValue & " (HTTPS)""")
    ElseIf bSuccess = true then
        objFile.Writeline ("      VALUE = ""The ConfigMgr Advanced Client has been successfully set to communicate with the MP on ports " & nPortValue & """")
    Else
        objFile.Writeline ("      VALUE = ""The ConfigMgr Advanced Client has not been set to communicate with the MP on the specified port.  See the client's Application Event Log for more details""")
    End If

    objFile.Writeline ("    END ATTRIBUTE")
    objFile.Writeline ("  END GROUP")
    objFile.Writeline ("END COMPONENT")

End Sub

'' SIG '' Begin signature block
'' SIG '' MIIoZwYJKoZIhvcNAQcCoIIoWDCCKFQCAQExDzANBglg
'' SIG '' hkgBZQMEAgEFADB3BgorBgEEAYI3AgEEoGkwZzAyBgor
'' SIG '' BgEEAYI3AgEeMCQCAQEEEE7wKRaZJ7VNj+Ws4Q8X66sC
'' SIG '' AQACAQACAQACAQACAQAwMTANBglghkgBZQMEAgEFAAQg
'' SIG '' kNoyQ+kEDMJy5X6lruwNc6Pgdomi/DC06UKEA/dNZYmg
'' SIG '' gg2FMIIGAzCCA+ugAwIBAgITMwAABISY4hLgeKMxXQAA
'' SIG '' AAAEhDANBgkqhkiG9w0BAQsFADB+MQswCQYDVQQGEwJV
'' SIG '' UzETMBEGA1UECBMKV2FzaGluZ3RvbjEQMA4GA1UEBxMH
'' SIG '' UmVkbW9uZDEeMBwGA1UEChMVTWljcm9zb2Z0IENvcnBv
'' SIG '' cmF0aW9uMSgwJgYDVQQDEx9NaWNyb3NvZnQgQ29kZSBT
'' SIG '' aWduaW5nIFBDQSAyMDExMB4XDTI1MDYxOTE4MjEzNVoX
'' SIG '' DTI2MDYxNzE4MjEzNVowdDELMAkGA1UEBhMCVVMxEzAR
'' SIG '' BgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcTB1JlZG1v
'' SIG '' bmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jwb3JhdGlv
'' SIG '' bjEeMBwGA1UEAxMVTWljcm9zb2Z0IENvcnBvcmF0aW9u
'' SIG '' MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA
'' SIG '' 7XpKjCg5837MnNU9UKR3xba/q5Iq/JXcyzypjF20Q6Ll
'' SIG '' VwLLwX3ehPNrT4+GM2kpbhg0KF9zaTCqKCnlRY4zUat+
'' SIG '' 8sk/4dUEyzAfHaZrGf+9FDPlP7GMb7dT1lsS4zDSF6sw
'' SIG '' fD4xuoux9mBYJOGDoXxknpL581td3SwLX4w9MIsERD7w
'' SIG '' jZYpUc+16BXXuSjtNXhYlnrXoePKlDqlGgJCM5wuFwd7
'' SIG '' BXdS1lJrqVxytOUHyUpp3ovamSQWE7fGYQKxg4e50J/m
'' SIG '' NYzgN6AYglCeJ9QjGlnQ4a4HTLrtNuqFgG3wt6a6pFJ/
'' SIG '' C1qdvB/tki3rTRuSkGWcL8t2XJ+/j0BpeQIDAQABo4IB
'' SIG '' gjCCAX4wHwYDVR0lBBgwFgYKKwYBBAGCN0wIAQYIKwYB
'' SIG '' BQUHAwMwHQYDVR0OBBYEFATf9G+hYepzHROBQMWBvZFg
'' SIG '' qW2FMFQGA1UdEQRNMEukSTBHMS0wKwYDVQQLEyRNaWNy
'' SIG '' b3NvZnQgSXJlbGFuZCBPcGVyYXRpb25zIExpbWl0ZWQx
'' SIG '' FjAUBgNVBAUTDTIzMDAxMis1MDUzNjIwHwYDVR0jBBgw
'' SIG '' FoAUSG5k5VAF04KqFzc3IrVtqMp1ApUwVAYDVR0fBE0w
'' SIG '' SzBJoEegRYZDaHR0cDovL3d3dy5taWNyb3NvZnQuY29t
'' SIG '' L3BraW9wcy9jcmwvTWljQ29kU2lnUENBMjAxMV8yMDEx
'' SIG '' LTA3LTA4LmNybDBhBggrBgEFBQcBAQRVMFMwUQYIKwYB
'' SIG '' BQUHMAKGRWh0dHA6Ly93d3cubWljcm9zb2Z0LmNvbS9w
'' SIG '' a2lvcHMvY2VydHMvTWljQ29kU2lnUENBMjAxMV8yMDEx
'' SIG '' LTA3LTA4LmNydDAMBgNVHRMBAf8EAjAAMA0GCSqGSIb3
'' SIG '' DQEBCwUAA4ICAQBi0KbNV1OEU3KAyAyz+kBtzZ0RN6f1
'' SIG '' kjKetQrPGfiVL98SVhrQc2JgiDZh1Rb+ovKWBf3u/RTS
'' SIG '' uj9aCo3bsah0onAXYPDI9JPJAxQP9HlNumzwUUFCGolq
'' SIG '' 4bAzq11nS5u2ZrudeqEKFFnCDbOIwX4wxFVeG5oEGH3v
'' SIG '' uPzFCcECfYepnxPpHAj+B5T+AoSEAVB6EspmpHEwb2cP
'' SIG '' kLLe7G3beSp0CpEhDdNQszxtWsApQiOsyyn/7yiMJ6h8
'' SIG '' P/lr3AK+4MCpVjZi8EzYvNO6/a1rF0HqdUPGDJCLhpmd
'' SIG '' GtagndxrjpEkc589v9KI3mVWIWcqIQkItQbPsX0ZL/38
'' SIG '' tB31d5jcjttnRVLx8wWYKhORWxo5lJ60q9cfJQqyvrOA
'' SIG '' PmzhqdiHozqYVqGRDxjnKPxxM52eS5OsOlvhNictzx6B
'' SIG '' RNGPE7ZEhOP/NGNpQSYS49u3fLnifCHUIUqS/1s04457
'' SIG '' mB+w8eaPaVnSBkmhTWLkqjmMa1VuzeABEFUQ2Xqg3H6j
'' SIG '' xtzuq+UjbMV23e9QwiEFEbVCrLOdzjfr65VdK44igSHc
'' SIG '' LzDS0PcytI8u+6MA8l16GJEMWpDdrhSATtVDQLwmF47O
'' SIG '' K8N0kZgV/aomeRDcXJ/6SzJIsm+vEHcB1F8/tXyOnmt/
'' SIG '' 446TT8+g5XP0THFyFnjDJIbqf1xG8Lu91Prs/zCCB3ow
'' SIG '' ggVioAMCAQICCmEOkNIAAAAAAAMwDQYJKoZIhvcNAQEL
'' SIG '' BQAwgYgxCzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpXYXNo
'' SIG '' aW5ndG9uMRAwDgYDVQQHEwdSZWRtb25kMR4wHAYDVQQK
'' SIG '' ExVNaWNyb3NvZnQgQ29ycG9yYXRpb24xMjAwBgNVBAMT
'' SIG '' KU1pY3Jvc29mdCBSb290IENlcnRpZmljYXRlIEF1dGhv
'' SIG '' cml0eSAyMDExMB4XDTExMDcwODIwNTkwOVoXDTI2MDcw
'' SIG '' ODIxMDkwOVowfjELMAkGA1UEBhMCVVMxEzARBgNVBAgT
'' SIG '' Cldhc2hpbmd0b24xEDAOBgNVBAcTB1JlZG1vbmQxHjAc
'' SIG '' BgNVBAoTFU1pY3Jvc29mdCBDb3Jwb3JhdGlvbjEoMCYG
'' SIG '' A1UEAxMfTWljcm9zb2Z0IENvZGUgU2lnbmluZyBQQ0Eg
'' SIG '' MjAxMTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoC
'' SIG '' ggIBAKvw+nIQHC6t2G6qghBNNLrytlghn0IbKmvpWlCq
'' SIG '' uAY4GgRJun/DDB7dN2vGEtgL8DjCmQawyDnVARQxQtOJ
'' SIG '' DXlkh36UYCRsr55JnOloXtLfm1OyCizDr9mpK656Ca/X
'' SIG '' llnKYBoF6WZ26DJSJhIv56sIUM+zRLdd2MQuA3WraPPL
'' SIG '' bfM6XKEW9Ea64DhkrG5kNXimoGMPLdNAk/jj3gcN1Vx5
'' SIG '' pUkp5w2+oBN3vpQ97/vjK1oQH01WKKJ6cuASOrdJXtjt
'' SIG '' 7UORg9l7snuGG9k+sYxd6IlPhBryoS9Z5JA7La4zWMW3
'' SIG '' Pv4y07MDPbGyr5I4ftKdgCz1TlaRITUlwzluZH9TupwP
'' SIG '' rRkjhMv0ugOGjfdf8NBSv4yUh7zAIXQlXxgotswnKDgl
'' SIG '' mDlKNs98sZKuHCOnqWbsYR9q4ShJnV+I4iVd0yFLPlLE
'' SIG '' tVc/JAPw0XpbL9Uj43BdD1FGd7P4AOG8rAKCX9vAFbO9
'' SIG '' G9RVS+c5oQ/pI0m8GLhEfEXkwcNyeuBy5yTfv0aZxe/C
'' SIG '' HFfbg43sTUkwp6uO3+xbn6/83bBm4sGXgXvt1u1L50kp
'' SIG '' pxMopqd9Z4DmimJ4X7IvhNdXnFy/dygo8e1twyiPLI9A
'' SIG '' N0/B4YVEicQJTMXUpUMvdJX3bvh4IFgsE11glZo+TzOE
'' SIG '' 2rCIF96eTvSWsLxGoGyY0uDWiIwLAgMBAAGjggHtMIIB
'' SIG '' 6TAQBgkrBgEEAYI3FQEEAwIBADAdBgNVHQ4EFgQUSG5k
'' SIG '' 5VAF04KqFzc3IrVtqMp1ApUwGQYJKwYBBAGCNxQCBAwe
'' SIG '' CgBTAHUAYgBDAEEwCwYDVR0PBAQDAgGGMA8GA1UdEwEB
'' SIG '' /wQFMAMBAf8wHwYDVR0jBBgwFoAUci06AjGQQ7kUBU7h
'' SIG '' 6qfHMdEjiTQwWgYDVR0fBFMwUTBPoE2gS4ZJaHR0cDov
'' SIG '' L2NybC5taWNyb3NvZnQuY29tL3BraS9jcmwvcHJvZHVj
'' SIG '' dHMvTWljUm9vQ2VyQXV0MjAxMV8yMDExXzAzXzIyLmNy
'' SIG '' bDBeBggrBgEFBQcBAQRSMFAwTgYIKwYBBQUHMAKGQmh0
'' SIG '' dHA6Ly93d3cubWljcm9zb2Z0LmNvbS9wa2kvY2VydHMv
'' SIG '' TWljUm9vQ2VyQXV0MjAxMV8yMDExXzAzXzIyLmNydDCB
'' SIG '' nwYDVR0gBIGXMIGUMIGRBgkrBgEEAYI3LgMwgYMwPwYI
'' SIG '' KwYBBQUHAgEWM2h0dHA6Ly93d3cubWljcm9zb2Z0LmNv
'' SIG '' bS9wa2lvcHMvZG9jcy9wcmltYXJ5Y3BzLmh0bTBABggr
'' SIG '' BgEFBQcCAjA0HjIgHQBMAGUAZwBhAGwAXwBwAG8AbABp
'' SIG '' AGMAeQBfAHMAdABhAHQAZQBtAGUAbgB0AC4gHTANBgkq
'' SIG '' hkiG9w0BAQsFAAOCAgEAZ/KGpZjgVHkaLtPYdGcimwuW
'' SIG '' EeFjkplCln3SeQyQwWVfLiw++MNy0W2D/r4/6ArKO79H
'' SIG '' qaPzadtjvyI1pZddZYSQfYtGUFXYDJJ80hpLHPM8QotS
'' SIG '' 0LD9a+M+By4pm+Y9G6XUtR13lDni6WTJRD14eiPzE32m
'' SIG '' kHSDjfTLJgJGKsKKELukqQUMm+1o+mgulaAqPyprWElj
'' SIG '' HwlpblqYluSD9MCP80Yr3vw70L01724lruWvJ+3Q3fMO
'' SIG '' r5kol5hNDj0L8giJ1h/DMhji8MUtzluetEk5CsYKwsat
'' SIG '' ruWy2dsViFFFWDgycScaf7H0J/jeLDogaZiyWYlobm+n
'' SIG '' t3TDQAUGpgEqKD6CPxNNZgvAs0314Y9/HG8VfUWnduVA
'' SIG '' KmWjw11SYobDHWM2l4bf2vP48hahmifhzaWX0O5dY0Hj
'' SIG '' Wwechz4GdwbRBrF1HxS+YWG18NzGGwS+30HHDiju3mUv
'' SIG '' 7Jf2oVyW2ADWoUa9WfOXpQlLSBCZgB/QACnFsZulP0V3
'' SIG '' HjXG0qKin3p6IvpIlR+r+0cjgPWe+L9rt0uX4ut1eBrs
'' SIG '' 6jeZeRhL/9azI2h15q/6/IvrC4DqaTuv/DDtBEyO3991
'' SIG '' bWORPdGdVk5Pv4BXIqF4ETIheu9BCrE/+6jMpF3BoYib
'' SIG '' V3FWTkhFwELJm3ZbCoBIa/15n8G9bW1qyVJzEw16UM0x
'' SIG '' gho6MIIaNgIBATCBlTB+MQswCQYDVQQGEwJVUzETMBEG
'' SIG '' A1UECBMKV2FzaGluZ3RvbjEQMA4GA1UEBxMHUmVkbW9u
'' SIG '' ZDEeMBwGA1UEChMVTWljcm9zb2Z0IENvcnBvcmF0aW9u
'' SIG '' MSgwJgYDVQQDEx9NaWNyb3NvZnQgQ29kZSBTaWduaW5n
'' SIG '' IFBDQSAyMDExAhMzAAAEhJjiEuB4ozFdAAAAAASEMA0G
'' SIG '' CWCGSAFlAwQCAQUAoIHeMBkGCSqGSIb3DQEJAzEMBgor
'' SIG '' BgEEAYI3AgEEMBwGCisGAQQBgjcCAQsxDjAMBgorBgEE
'' SIG '' AYI3AgEVMC8GCSqGSIb3DQEJBDEiBCA0WmhIyaCB433Q
'' SIG '' btKGvSlstI+NGeScr9S1mJTSgSORSDByBgorBgEEAYI3
'' SIG '' AgEMMWQwYqBEgEIARABlAHMAawB0AG8AcABBAG4AYQBs
'' SIG '' AHkAdABpAGMAcwBMAG8AZwBzAEMAbwBsAGwAZQBjAHQA
'' SIG '' bwByAC4AcABzADGhGoAYaHR0cDovL3d3dy5taWNyb3Nv
'' SIG '' ZnQuY29tMA0GCSqGSIb3DQEBAQUABIIBAG5FpQ/q4nzh
'' SIG '' KqVk20g1ctofM7+6TWlsxguB0bRbQC3HO8WAyoxz+QRF
'' SIG '' UfX31FpD4lqy1YiXfKNVHNzs8Xwc253MrVXrO1tvykxk
'' SIG '' U6Enejx5/UONAU+krxCjxIdJ54x6sO1S5OA/LyFzSPdz
'' SIG '' gEfLOUO7wHrYi/LMEtuv2UzAz5siZ4bZ2jYhdpY281f1
'' SIG '' z8JHn0vo0uw0HiUofRrp5dW4mrX3e08Rk4QdmHGI4RGg
'' SIG '' R3V3m46NkWy6pTLkixlw2QjZR79gW6PytV4gcjqfjlc9
'' SIG '' I6hpdyJVmQJ2PewXf74vry14W95t2KJYGRW2h8uUw955
'' SIG '' f+nZ04P6NIuertf56W3Iu5KhgheUMIIXkAYKKwYBBAGC
'' SIG '' NwMDATGCF4Awghd8BgkqhkiG9w0BBwKgghdtMIIXaQIB
'' SIG '' AzEPMA0GCWCGSAFlAwQCAQUAMIIBUgYLKoZIhvcNAQkQ
'' SIG '' AQSgggFBBIIBPTCCATkCAQEGCisGAQQBhFkKAwEwMTAN
'' SIG '' BglghkgBZQMEAgEFAAQglG4/YF633IoCX/6KBtmwILdS
'' SIG '' oSEjeYTiOD7LCpk4pyYCBmjJgiX6JRgTMjAyNTA5MjYx
'' SIG '' NDU1MjYuMTA3WjAEgAIB9KCB0aSBzjCByzELMAkGA1UE
'' SIG '' BhMCVVMxEzARBgNVBAgTCldhc2hpbmd0b24xEDAOBgNV
'' SIG '' BAcTB1JlZG1vbmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBD
'' SIG '' b3Jwb3JhdGlvbjElMCMGA1UECxMcTWljcm9zb2Z0IEFt
'' SIG '' ZXJpY2EgT3BlcmF0aW9uczEnMCUGA1UECxMeblNoaWVs
'' SIG '' ZCBUU1MgRVNOOkEwMDAtMDVFMC1EOTQ3MSUwIwYDVQQD
'' SIG '' ExxNaWNyb3NvZnQgVGltZS1TdGFtcCBTZXJ2aWNloIIR
'' SIG '' 6jCCByAwggUIoAMCAQICEzMAAAIIeJ1YXZLH2VIAAQAA
'' SIG '' AggwDQYJKoZIhvcNAQELBQAwfDELMAkGA1UEBhMCVVMx
'' SIG '' EzARBgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcTB1Jl
'' SIG '' ZG1vbmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jwb3Jh
'' SIG '' dGlvbjEmMCQGA1UEAxMdTWljcm9zb2Z0IFRpbWUtU3Rh
'' SIG '' bXAgUENBIDIwMTAwHhcNMjUwMTMwMTk0MjUzWhcNMjYw
'' SIG '' NDIyMTk0MjUzWjCByzELMAkGA1UEBhMCVVMxEzARBgNV
'' SIG '' BAgTCldhc2hpbmd0b24xEDAOBgNVBAcTB1JlZG1vbmQx
'' SIG '' HjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jwb3JhdGlvbjEl
'' SIG '' MCMGA1UECxMcTWljcm9zb2Z0IEFtZXJpY2EgT3BlcmF0
'' SIG '' aW9uczEnMCUGA1UECxMeblNoaWVsZCBUU1MgRVNOOkEw
'' SIG '' MDAtMDVFMC1EOTQ3MSUwIwYDVQQDExxNaWNyb3NvZnQg
'' SIG '' VGltZS1TdGFtcCBTZXJ2aWNlMIICIjANBgkqhkiG9w0B
'' SIG '' AQEFAAOCAg8AMIICCgKCAgEAtctwCOZSM9yKdZyuQTFF
'' SIG '' GxkbI0pws/1RrN9872NDXrIbD4H5Xd/2d/93UvFigS5Q
'' SIG '' 5aLJlyTmZRUojV1Heg0ycQPYpP2WwnVie/Cyo2zd7RZF
'' SIG '' 9nOkUaUTKQPLKv6AW0a8j93PEP4MaSQChx8/HLkp+3sH
'' SIG '' wi85zZsapYk5N0OSx6s9j43mCg/3WyjAU9kwAFgL7puM
'' SIG '' /x1yCerRXRqDVeFlEWbMAkrekTsGqkNaAGBrxJ3R/g12
'' SIG '' atfmx7IL3DzQnU0iKVqG0IiUv1Ci4kdNijQqgeCPcmox
'' SIG '' U0pZzCBDM/zYud/KBiOuKYXLzaVHtvqmilh2fHeE9SoI
'' SIG '' b0ZkkheGBeQzRCW8WglMLMu51C5rBZ02jo1TqExVln1l
'' SIG '' 7wbjipAXEClhir65Ive+o+MfuXswD9+n6t7unR0SUy2Q
'' SIG '' LuHRLjqKFN/pDGa/kQWFo0x0AilfsmdUk9HhpGx16ANp
'' SIG '' cskQ5TYwUHKHmSMVgmbbP3d/p39Y4kizen+sHR2lM9AA
'' SIG '' 8Dk0P2hKNSAvOXhXj78iCmsRSZBlNjKmul86t6gqubaJ
'' SIG '' CB7Y4aILKxIHwyk3hV07XYZdSD7S3AnzHFjhhgF6LFVF
'' SIG '' OxvePBelveuNuH9lRw/C9xaMgCPfq+M8iEFJqohEs7kF
'' SIG '' nlqU04xWMApoF2hjrkg1fHDTlUAeiD8z53mYVU48MWwG
'' SIG '' ZWkCAwEAAaOCAUkwggFFMB0GA1UdDgQWBBSjMeL3zqnF
'' SIG '' E4GDlQfX9fP5oXoBTTAfBgNVHSMEGDAWgBSfpxVdAF5i
'' SIG '' XYP05dJlpxtTNRnpcjBfBgNVHR8EWDBWMFSgUqBQhk5o
'' SIG '' dHRwOi8vd3d3Lm1pY3Jvc29mdC5jb20vcGtpb3BzL2Ny
'' SIG '' bC9NaWNyb3NvZnQlMjBUaW1lLVN0YW1wJTIwUENBJTIw
'' SIG '' MjAxMCgxKS5jcmwwbAYIKwYBBQUHAQEEYDBeMFwGCCsG
'' SIG '' AQUFBzAChlBodHRwOi8vd3d3Lm1pY3Jvc29mdC5jb20v
'' SIG '' cGtpb3BzL2NlcnRzL01pY3Jvc29mdCUyMFRpbWUtU3Rh
'' SIG '' bXAlMjBQQ0ElMjAyMDEwKDEpLmNydDAMBgNVHRMBAf8E
'' SIG '' AjAAMBYGA1UdJQEB/wQMMAoGCCsGAQUFBwMIMA4GA1Ud
'' SIG '' DwEB/wQEAwIHgDANBgkqhkiG9w0BAQsFAAOCAgEAUbMy
'' SIG '' iSsAH7MKnWkDxYmmAf2TQGFg2tONF03ELAmgrmuZ7BtS
'' SIG '' LJWGkqR+5oky6+nkBKl3M2aKnjmv8bw5zBonxjXWtAh2
'' SIG '' 0MLaZyIbLrayjto4YxGhsJSYDjKpdta+yJOl5wc2tHt4
'' SIG '' QTruFAZDJfyxF/gFEbe4u/kUzbBjdHFz8D0m0xRPvc+1
'' SIG '' moBm2PacFKPzcZBibHqhgkP/StlTFO+G8OXu/vCBlITN
'' SIG '' sbKST6p0nhz4WJnAdFnJTsXFSH4/2bkL8KKz20xBGA1Q
'' SIG '' s0jd+3NMgoTzGOxSfhxhQTSccHeZSiK+xmH6vGtIDogt
'' SIG '' pYxmJXOK7eHAnndVyoPN39JfWlFYplgWF7XzXm4aX6+i
'' SIG '' 3N4w/DYLKw4c7dFoJyHZ02Qou48Y7CAYpR/faWOf4em0
'' SIG '' HCyivxOigj/RNWDe/Hy2jl5FzMjusS670GfrgkotYXU7
'' SIG '' nxQu6EgfwlOUW3yFR1xtI9aNp9bZ3uHgmzXyqlD0xN9b
'' SIG '' TW1gUdt2IstK95EJh3mBNRi2y+KcJJ6moqdQUZ+liFDC
'' SIG '' bYJ3GsBDd93/AGBmeGtzZx6KcxlVep3n3xlWoOE3bsvq
'' SIG '' MtWBfrIQoaF3TKn4T1haR3t7iRk+BiRIjbOPtvGv8B1L
'' SIG '' hfmkWkdHDeT+15TsFNd+tIlAibUHbykGjQMBiNvSjsEt
'' SIG '' 0Bq4kfRdozhj1AJaXhMwggdxMIIFWaADAgECAhMzAAAA
'' SIG '' FcXna54Cm0mZAAAAAAAVMA0GCSqGSIb3DQEBCwUAMIGI
'' SIG '' MQswCQYDVQQGEwJVUzETMBEGA1UECBMKV2FzaGluZ3Rv
'' SIG '' bjEQMA4GA1UEBxMHUmVkbW9uZDEeMBwGA1UEChMVTWlj
'' SIG '' cm9zb2Z0IENvcnBvcmF0aW9uMTIwMAYDVQQDEylNaWNy
'' SIG '' b3NvZnQgUm9vdCBDZXJ0aWZpY2F0ZSBBdXRob3JpdHkg
'' SIG '' MjAxMDAeFw0yMTA5MzAxODIyMjVaFw0zMDA5MzAxODMy
'' SIG '' MjVaMHwxCzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpXYXNo
'' SIG '' aW5ndG9uMRAwDgYDVQQHEwdSZWRtb25kMR4wHAYDVQQK
'' SIG '' ExVNaWNyb3NvZnQgQ29ycG9yYXRpb24xJjAkBgNVBAMT
'' SIG '' HU1pY3Jvc29mdCBUaW1lLVN0YW1wIFBDQSAyMDEwMIIC
'' SIG '' IjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEA5OGm
'' SIG '' TOe0ciELeaLL1yR5vQ7VgtP97pwHB9KpbE51yMo1V/YB
'' SIG '' f2xK4OK9uT4XYDP/XE/HZveVU3Fa4n5KWv64NmeFRiMM
'' SIG '' tY0Tz3cywBAY6GB9alKDRLemjkZrBxTzxXb1hlDcwUTI
'' SIG '' cVxRMTegCjhuje3XD9gmU3w5YQJ6xKr9cmmvHaus9ja+
'' SIG '' NSZk2pg7uhp7M62AW36MEBydUv626GIl3GoPz130/o5T
'' SIG '' z9bshVZN7928jaTjkY+yOSxRnOlwaQ3KNi1wjjHINSi9
'' SIG '' 47SHJMPgyY9+tVSP3PoFVZhtaDuaRr3tpK56KTesy+uD
'' SIG '' RedGbsoy1cCGMFxPLOJiss254o2I5JasAUq7vnGpF1tn
'' SIG '' YN74kpEeHT39IM9zfUGaRnXNxF803RKJ1v2lIH1+/Nme
'' SIG '' Rd+2ci/bfV+AutuqfjbsNkz2K26oElHovwUDo9Fzpk03
'' SIG '' dJQcNIIP8BDyt0cY7afomXw/TNuvXsLz1dhzPUNOwTM5
'' SIG '' TI4CvEJoLhDqhFFG4tG9ahhaYQFzymeiXtcodgLiMxhy
'' SIG '' 16cg8ML6EgrXY28MyTZki1ugpoMhXV8wdJGUlNi5UPkL
'' SIG '' iWHzNgY1GIRH29wb0f2y1BzFa/ZcUlFdEtsluq9QBXps
'' SIG '' xREdcu+N+VLEhReTwDwV2xo3xwgVGD94q0W29R6HXtqP
'' SIG '' nhZyacaue7e3PmriLq0CAwEAAaOCAd0wggHZMBIGCSsG
'' SIG '' AQQBgjcVAQQFAgMBAAEwIwYJKwYBBAGCNxUCBBYEFCqn
'' SIG '' Uv5kxJq+gpE8RjUpzxD/LwTuMB0GA1UdDgQWBBSfpxVd
'' SIG '' AF5iXYP05dJlpxtTNRnpcjBcBgNVHSAEVTBTMFEGDCsG
'' SIG '' AQQBgjdMg30BATBBMD8GCCsGAQUFBwIBFjNodHRwOi8v
'' SIG '' d3d3Lm1pY3Jvc29mdC5jb20vcGtpb3BzL0RvY3MvUmVw
'' SIG '' b3NpdG9yeS5odG0wEwYDVR0lBAwwCgYIKwYBBQUHAwgw
'' SIG '' GQYJKwYBBAGCNxQCBAweCgBTAHUAYgBDAEEwCwYDVR0P
'' SIG '' BAQDAgGGMA8GA1UdEwEB/wQFMAMBAf8wHwYDVR0jBBgw
'' SIG '' FoAU1fZWy4/oolxiaNE9lJBb186aGMQwVgYDVR0fBE8w
'' SIG '' TTBLoEmgR4ZFaHR0cDovL2NybC5taWNyb3NvZnQuY29t
'' SIG '' L3BraS9jcmwvcHJvZHVjdHMvTWljUm9vQ2VyQXV0XzIw
'' SIG '' MTAtMDYtMjMuY3JsMFoGCCsGAQUFBwEBBE4wTDBKBggr
'' SIG '' BgEFBQcwAoY+aHR0cDovL3d3dy5taWNyb3NvZnQuY29t
'' SIG '' L3BraS9jZXJ0cy9NaWNSb29DZXJBdXRfMjAxMC0wNi0y
'' SIG '' My5jcnQwDQYJKoZIhvcNAQELBQADggIBAJ1VffwqreEs
'' SIG '' H2cBMSRb4Z5yS/ypb+pcFLY+TkdkeLEGk5c9MTO1OdfC
'' SIG '' cTY/2mRsfNB1OW27DzHkwo/7bNGhlBgi7ulmZzpTTd2Y
'' SIG '' urYeeNg2LpypglYAA7AFvonoaeC6Ce5732pvvinLbtg/
'' SIG '' SHUB2RjebYIM9W0jVOR4U3UkV7ndn/OOPcbzaN9l9qRW
'' SIG '' qveVtihVJ9AkvUCgvxm2EhIRXT0n4ECWOKz3+SmJw7wX
'' SIG '' sFSFQrP8DJ6LGYnn8AtqgcKBGUIZUnWKNsIdw2FzLixr
'' SIG '' e24/LAl4FOmRsqlb30mjdAy87JGA0j3mSj5mO0+7hvoy
'' SIG '' GtmW9I/2kQH2zsZ0/fZMcm8Qq3UwxTSwethQ/gpY3UA8
'' SIG '' x1RtnWN0SCyxTkctwRQEcb9k+SS+c23Kjgm9swFXSVRk
'' SIG '' 2XPXfx5bRAGOWhmRaw2fpCjcZxkoJLo4S5pu+yFUa2pF
'' SIG '' EUep8beuyOiJXk+d0tBMdrVXVAmxaQFEfnyhYWxz/gq7
'' SIG '' 7EFmPWn9y8FBSX5+k77L+DvktxW/tM4+pTFRhLy/AsGC
'' SIG '' onsXHRWJjXD+57XQKBqJC4822rpM+Zv/Cuk0+CQ1Zyvg
'' SIG '' DbjmjJnW4SLq8CdCPSWU5nR0W2rRnj7tfqAxM328y+l7
'' SIG '' vzhwRNGQ8cirOoo6CGJ/2XBjU02N7oJtpQUQwXEGahC0
'' SIG '' HVUzWLOhcGbyoYIDTTCCAjUCAQEwgfmhgdGkgc4wgcsx
'' SIG '' CzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpXYXNoaW5ndG9u
'' SIG '' MRAwDgYDVQQHEwdSZWRtb25kMR4wHAYDVQQKExVNaWNy
'' SIG '' b3NvZnQgQ29ycG9yYXRpb24xJTAjBgNVBAsTHE1pY3Jv
'' SIG '' c29mdCBBbWVyaWNhIE9wZXJhdGlvbnMxJzAlBgNVBAsT
'' SIG '' Hm5TaGllbGQgVFNTIEVTTjpBMDAwLTA1RTAtRDk0NzEl
'' SIG '' MCMGA1UEAxMcTWljcm9zb2Z0IFRpbWUtU3RhbXAgU2Vy
'' SIG '' dmljZaIjCgEBMAcGBSsOAwIaAxUAjZL7tDSnEo3WCsq4
'' SIG '' SWXLMlzlEzSggYMwgYCkfjB8MQswCQYDVQQGEwJVUzET
'' SIG '' MBEGA1UECBMKV2FzaGluZ3RvbjEQMA4GA1UEBxMHUmVk
'' SIG '' bW9uZDEeMBwGA1UEChMVTWljcm9zb2Z0IENvcnBvcmF0
'' SIG '' aW9uMSYwJAYDVQQDEx1NaWNyb3NvZnQgVGltZS1TdGFt
'' SIG '' cCBQQ0EgMjAxMDANBgkqhkiG9w0BAQsFAAIFAOyAhYww
'' SIG '' IhgPMjAyNTA5MjYwMzIyNTJaGA8yMDI1MDkyNzAzMjI1
'' SIG '' MlowdDA6BgorBgEEAYRZCgQBMSwwKjAKAgUA7ICFjAIB
'' SIG '' ADAHAgEAAgIlTDAHAgEAAgISOzAKAgUA7IHXDAIBADA2
'' SIG '' BgorBgEEAYRZCgQCMSgwJjAMBgorBgEEAYRZCgMCoAow
'' SIG '' CAIBAAIDB6EgoQowCAIBAAIDAYagMA0GCSqGSIb3DQEB
'' SIG '' CwUAA4IBAQDHwdakAd2Q1l3DE8BczJYsicC2aO3HJ9H5
'' SIG '' 0pBMNEaZSPVG75wwi1GPZUCYEZN5y8sFy88X5C9AGPCo
'' SIG '' YPZItzicNKpCTvQ4hzy26FRnwKcHsjhOVgf519+MLg1H
'' SIG '' ue68W3IWWgXEvIMbiy+UmkM+s4aL2xIaFNJwIFz50ced
'' SIG '' nU/Pvi6C2HjF26pOwKyh9mdhkb/VAaCJzrZIvxNrtdeM
'' SIG '' 6NSfOEn8ZcnnzVrg2AHKedlG7Q2juxYJeZHaslSQltKh
'' SIG '' djDD0D8diKmDVEKE9p2kqnP2wzlwtdDPnh3mkIyZHg/Y
'' SIG '' m3rnpwxfl/NQac2NQ5DWHhf65V4L57165jyA/FoXmDCS
'' SIG '' MYIEDTCCBAkCAQEwgZMwfDELMAkGA1UEBhMCVVMxEzAR
'' SIG '' BgNVBAgTCldhc2hpbmd0b24xEDAOBgNVBAcTB1JlZG1v
'' SIG '' bmQxHjAcBgNVBAoTFU1pY3Jvc29mdCBDb3Jwb3JhdGlv
'' SIG '' bjEmMCQGA1UEAxMdTWljcm9zb2Z0IFRpbWUtU3RhbXAg
'' SIG '' UENBIDIwMTACEzMAAAIIeJ1YXZLH2VIAAQAAAggwDQYJ
'' SIG '' YIZIAWUDBAIBBQCgggFKMBoGCSqGSIb3DQEJAzENBgsq
'' SIG '' hkiG9w0BCRABBDAvBgkqhkiG9w0BCQQxIgQgElYXfmVm
'' SIG '' Uaol/FwlpSMNwvbrttoXDmurZw+patngqCswgfoGCyqG
'' SIG '' SIb3DQEJEAIvMYHqMIHnMIHkMIG9BCCP/45vCR2tltTv
'' SIG '' e+/LffhbdmeTZiqrbT5OkPvUUaZnqTCBmDCBgKR+MHwx
'' SIG '' CzAJBgNVBAYTAlVTMRMwEQYDVQQIEwpXYXNoaW5ndG9u
'' SIG '' MRAwDgYDVQQHEwdSZWRtb25kMR4wHAYDVQQKExVNaWNy
'' SIG '' b3NvZnQgQ29ycG9yYXRpb24xJjAkBgNVBAMTHU1pY3Jv
'' SIG '' c29mdCBUaW1lLVN0YW1wIFBDQSAyMDEwAhMzAAACCHid
'' SIG '' WF2Sx9lSAAEAAAIIMCIEIMms+JaQFd/53grMC/Now0Se
'' SIG '' NkAeLZmbu+SKClmDJaFIMA0GCSqGSIb3DQEBCwUABIIC
'' SIG '' AD9r9EpRKRUdMifiFNDT2dsr3NzHCbAf8TBnuPzI1iBH
'' SIG '' BSwqjik+e0EJbYayPrjntRWA9HPuzOSpwyid/lKi5l3W
'' SIG '' Ay2TnP9Yl71MxJ61jR/LuKDXXGJdYPmvOTO1cTWHrD/u
'' SIG '' FTamYyUTamP5XFmrZGnwHh8JpwZf2nM2ZwnR3CgHsRkw
'' SIG '' zHoya9sjobUpM3rovUGnpHKexKh7Du9hjNQfFzLDs2u6
'' SIG '' 1aPDtbrnICuRguSwb0vGray67bPS13ItNp5M6G6HifRT
'' SIG '' JWcouiPODQykcbsgo+k4rpa8E2E/4GB46fOpV8sK1Xvi
'' SIG '' wrcy3BZK+f82LDnHqH1lufJvhHt6cUXl1bTOIREWrURl
'' SIG '' NqeI/9xxVQSwbaV7WouyvJHb7VlrNAjerOeojNt6DsGf
'' SIG '' YrAe+whXW11b8N+URmxBEX/9V16IKA0YJ0hQa8wdh46D
'' SIG '' 8TBzjjRN1qOLrKz2lsUJBOSQrPG7e1YHH7Sv8hYuKUhN
'' SIG '' oFdZEIZGK77jMx/LdkAj6X8LWwZdh8bg1i/0Xog0eJTG
'' SIG '' B5VEvwYqrPiAZOdUWjfKHHpZ7T9kZar1b5t9QOFRPOfx
'' SIG '' KFHgHUQiqysJdbvCX7L+oyRT6Qo5aCr5YTx1h87Cv66y
'' SIG '' dJd6vp2HICcQag0CNFIRDceE2w6wuAEkY0zGLcJKDJku
'' SIG '' LBe2g9POPJD24whRUq88bXzZ
'' SIG '' End signature block
