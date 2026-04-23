Dim ws, port, i, ready, r
Set ws = CreateObject("WScript.Shell")
port = 8889

Function PortListening(p)
    r = ws.Exec("cmd /c netstat -ano | findstr :" & p & " | findstr LISTENING").StdOut.ReadAll()
    PortListening = (InStr(r, CStr(p)) > 0)
End Function

' Start main app
If Not PortListening(port) Then
    ws.Run "cmd /k cd /d d:/AAgent && python -X utf8 -u app.py", 1, False
    ready = False
    For i = 1 To 20
        WScript.Sleep 1000
        If PortListening(port) Then
            ready = True
            Exit For
        End If
    Next
    If Not ready Then
        MsgBox "Server start timeout. Check log window.", 16, "Error"
        WScript.Quit
    End If
End If

' Open browser
WScript.Sleep 2000
ws.Run "cmd /c start http://127.0.0.1:" & port, 0, False
