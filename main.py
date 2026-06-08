package com.mrsk.pcmonitor

import android.app.*
import android.app.DatePickerDialog
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.*
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {

    private lateinit var pcsContainer: LinearLayout
    private var currentTab = 0
    private lateinit var apiClient: ZabbixApiClient
    private lateinit var prefs: SharedPreferences
    private var userRole: String = "reader"

    private val allMessages = mutableListOf<ZabbixMessage>()
    private val unreadMessages = mutableListOf<ZabbixMessage>()
    private val activeTasks = mutableListOf<FixTask>()
    private val archivedTasks = mutableListOf<FixTask>()
    private val readMessageIds = mutableSetOf<String>()
    private val handler = Handler(Looper.getMainLooper())
    private var lastUnreadCount = 0

    private var activeTasksSortOrder = "desc"
    private var archiveFilter = "all"
    private var rangeStart: Long? = null
    private var rangeEnd: Long? = null

    private lateinit var usersRecyclerView: RecyclerView
    private lateinit var userAdapter: UserAdapter
    private val usersList = mutableListOf<User>()

    companion object {
        private const val NOTIFICATION_CHANNEL_ID = "zabbix_channel"
        private const val CHECK_INTERVAL = 30000L
        private const val PERMISSION_REQUEST_CODE = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        userRole = intent.getStringExtra("user_role") ?: "reader"
        windowSettings()
        prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        val token = prefs.getString("token", null)
        apiClient = ZabbixApiClient(this)
        if (token != null) apiClient.setAuthToken(token)

        createNotificationChannel()
        requestNotificationPermission()
        showMainScreen()
        startBackgroundCheck()
        loadAllData()
    }

    private fun windowSettings() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
        } else {
            @Suppress("DEPRECATION")
            window.setFlags(
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
            )
        }
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.parseColor("#231F20")
    }

    private fun loadAllData() {
        loadTasks()
        loadMessages()
    }

    private fun loadTasks() {
        apiClient.getTasks(object : ZabbixApiClient.Callback<List<FixTask>> {
            override fun onSuccess(tasks: List<FixTask>) {
                activeTasks.clear()
                archivedTasks.clear()
                for (task in tasks) {
                    if (task.completedAt == null) activeTasks.add(task)
                    else archivedTasks.add(task)
                }
                runOnUiThread {
                    if (currentTab == 0) displayActiveTasks()
                    if (currentTab == 3) displayArchive()
                    if (currentTab == 1) displayStatistics()
                }
            }
            override fun onError(error: String) {
                runOnUiThread { Toast.makeText(this@MainActivity, "Ошибка загрузки задач: $error", Toast.LENGTH_SHORT).show() }
            }
        })
    }

    private fun loadMessages() {
        apiClient.getMessages(object : ZabbixApiClient.Callback<List<ZabbixMessage>> {
            override fun onSuccess(messages: List<ZabbixMessage>) {
                allMessages.clear()
                allMessages.addAll(messages)
                unreadMessages.clear()
                unreadMessages.addAll(messages.filter { !it.isRead })
                readMessageIds.clear()
                readMessageIds.addAll(messages.filter { it.isRead }.map { it.id })
                runOnUiThread {
                    if (currentTab == 2) displayUnreadMessages()
                    checkNewMessagesNotification(messages)
                }
            }
            override fun onError(error: String) {
                runOnUiThread { Toast.makeText(this@MainActivity, "Ошибка загрузки сообщений: $error", Toast.LENGTH_SHORT).show() }
            }
        })
    }

    private fun checkNewMessagesNotification(messages: List<ZabbixMessage>) {
        val unreadNow = messages.count { !it.isRead }
        if (unreadNow > lastUnreadCount) {
            val newMessages = messages.filter { !it.isRead }.take(unreadNow - lastUnreadCount)
            if (newMessages.isNotEmpty()) {
                showNotification(newMessages.last())
            }
        }
        lastUnreadCount = unreadNow
    }

    private fun startBackgroundCheck() {
        handler.post(object : Runnable {
            override fun run() {
                loadAllData()
                handler.postDelayed(this, CHECK_INTERVAL)
            }
        })
    }

    private fun showNotification(message: ZabbixMessage) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val intent = Intent(this, MainActivity::class.java).apply {
            putExtra("open_tab", 2)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Новое сообщение от Zabbix")
            .setContentText("${message.problemName} на ${message.hostName}")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).notify(System.currentTimeMillis().toInt(), notification)
    }

    private fun markTaskCompleted(task: FixTask) {
        apiClient.completeTask(task.id, object : ZabbixApiClient.Callback<Boolean> {
            override fun onSuccess(result: Boolean) {
                loadTasks()
                runOnUiThread { Toast.makeText(this@MainActivity, "Задача выполнена", Toast.LENGTH_SHORT).show() }
            }
            override fun onError(error: String) {
                runOnUiThread { Toast.makeText(this@MainActivity, "Ошибка: $error", Toast.LENGTH_SHORT).show() }
            }
        })
    }

    private fun restoreTask(task: FixTask) {
        apiClient.restoreTask(task.id, object : ZabbixApiClient.Callback<Boolean> {
            override fun onSuccess(result: Boolean) {
                loadTasks()
                runOnUiThread { Toast.makeText(this@MainActivity, "Задача восстановлена", Toast.LENGTH_SHORT).show() }
            }
            override fun onError(error: String) {
                runOnUiThread { Toast.makeText(this@MainActivity, "Ошибка: $error", Toast.LENGTH_SHORT).show() }
            }
        })
    }

    private fun markAllMessagesAsRead() {
        for (msg in unreadMessages) {
            apiClient.markMessageRead(msg.id, object : ZabbixApiClient.Callback<Boolean> {
                override fun onSuccess(result: Boolean) { }
                override fun onError(error: String) { }
            })
        }
        runOnUiThread { loadMessages() }
    }

    private fun loadUnreadMessages() {
        loadMessages()
    }

    // ========================= UI: Активные задачи =========================
    private fun displayActiveTasks() {
        pcsContainer.removeAllViews()
        val topPanel = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            setPadding(dpToPx(8), dpToPx(8), dpToPx(8), dpToPx(8))
        }
        val sortBtn = Button(this).apply {
            text = if (activeTasksSortOrder == "desc") "Новые ↓" else "Старые ↑"
            setOnClickListener {
                activeTasksSortOrder = if (activeTasksSortOrder == "desc") "asc" else "desc"
                displayActiveTasks()
            }
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dpToPx(40))
            background = createRoundedDrawable(Color.parseColor("#555555"), dpToPx(8))
            setTextColor(Color.WHITE)
        }
        topPanel.addView(sortBtn)
        pcsContainer.addView(topPanel)

        val sorted = if (activeTasksSortOrder == "desc") activeTasks.sortedByDescending { it.id } else activeTasks.sortedBy { it.id }
        if (sorted.isEmpty()) { showEmptyState("Нет активных задач"); return }
        pcsContainer.addView(titleView("АКТИВНЫЕ ЗАДАЧИ"))
        sorted.forEach { pcsContainer.addView(createTaskCard(it, false)) }
    }

    private fun createTaskCard(task: FixTask, isArchived: Boolean): LinearLayout {
        val severityColor = getSeverityColor(task.severity)
        return LinearLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { setMargins(0, 0, 0, dpToPx(8)) }
            orientation = LinearLayout.VERTICAL
            background = createRoundedDrawable(if (isArchived) Color.parseColor("#331F1B1A") else Color.parseColor("#2A2A2A"), dpToPx(12))
            setPadding(dpToPx(12), dpToPx(12), dpToPx(12), dpToPx(12))

            setOnClickListener {
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Детали задачи")
                    .setMessage("""
                        Хост: ${task.hostName}
                        Проблема: ${task.triggerName}
                        Важность: ${task.severity}
                        Описание: ${task.comments}
                        Время: ${formatTimestamp(task.timestamp)}
                    """.trimIndent())
                    .setPositiveButton("OK", null)
                    .show()
            }

            val topRow = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            val info = LinearLayout(this@MainActivity).apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                orientation = LinearLayout.VERTICAL
            }
            info.addView(textView(if (isArchived) "📦 ${task.hostName}" else "🔧 ${task.hostName}", 16f, true))
            info.addView(textView("⚠️ ${task.triggerName}", 13f, false).apply { setTextColor(Color.parseColor("#DDDDDD")); setPadding(0, dpToPx(4), 0, 0) })
            topRow.addView(info)
            topRow.addView(TextView(this@MainActivity).apply {
                layoutParams = LinearLayout.LayoutParams(dpToPx(90), dpToPx(32))
                text = task.severity
                textSize = 12f
                gravity = Gravity.CENTER
                setTextColor(Color.WHITE)
                background = createRoundedDrawable(severityColor, dpToPx(16))
            })
            val bottomRow = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, dpToPx(12), 0, 0)
            }
            bottomRow.addView(textView(formatTimestamp(task.timestamp), 11f, false).apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                setTextColor(Color.parseColor("#888888"))
            })
            bottomRow.addView(Button(this@MainActivity).apply {
                text = if (isArchived) "Восстановить" else "Выполнить"
                textSize = 12f
                setBackgroundColor(if (isArchived) Color.parseColor("#FF9800") else Color.parseColor("#4CAF50"))
                setTextColor(Color.WHITE)
                setPadding(dpToPx(12), dpToPx(6), dpToPx(12), dpToPx(6))
                background = createRoundedDrawable(if (isArchived) Color.parseColor("#FF9800") else Color.parseColor("#4CAF50"), dpToPx(20))
                setOnClickListener {
                    if (isArchived) restoreTask(task) else markTaskCompleted(task)
                }
            })
            addView(topRow)
            addView(bottomRow)
        }
    }

    // ========================= UI: Сообщения =========================
    private fun displayUnreadMessages() {
        pcsContainer.removeAllViews()
        if (unreadMessages.isEmpty()) { showEmptyState("Нет новых сообщений"); return }
        pcsContainer.addView(Button(this).apply {
            text = "Обновить"
            setOnClickListener { loadMessages() }
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dpToPx(40)).apply { setMargins(dpToPx(8), dpToPx(8), dpToPx(8), dpToPx(8)) }
            background = createRoundedDrawable(Color.parseColor("#555555"), dpToPx(8))
            setTextColor(Color.WHITE)
        })
        pcsContainer.addView(Button(this).apply {
            text = "Отметить все как прочитанные"
            setOnClickListener { markAllMessagesAsRead() }
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dpToPx(40)).apply { setMargins(dpToPx(8), dpToPx(8), dpToPx(8), dpToPx(8)) }
            background = createRoundedDrawable(Color.parseColor("#3F51B5"), dpToPx(8))
            setTextColor(Color.WHITE)
        })
        unreadMessages.forEach { pcsContainer.addView(createMessageCard(it)) }
    }

    private fun createMessageCard(msg: ZabbixMessage): LinearLayout {
        val severityColor = getSeverityColor(msg.severity)
        return LinearLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { setMargins(0, 0, 0, dpToPx(8)) }
            orientation = LinearLayout.VERTICAL
            background = createRoundedDrawable(Color.parseColor("#331F1B1A"), dpToPx(12))
            isClickable = true
            val topRow = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(dpToPx(12), dpToPx(12), dpToPx(12), dpToPx(12))
            }
            val info = LinearLayout(this@MainActivity).apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                orientation = LinearLayout.VERTICAL
            }
            val nameRow = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            nameRow.addView(textView(getStatusEmoji(msg.severity), 16f, false).apply { setPadding(0, 0, dpToPx(8), 0) })
            nameRow.addView(textView(msg.hostName, 15f, true).apply { layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f) })
            info.addView(nameRow)
            info.addView(textView("⚠️ ${msg.problemName}", 12f, false).apply { setTextColor(Color.parseColor("#AAAAAA")); setPadding(0, dpToPx(4), 0, 0) })
            topRow.addView(info)
            topRow.addView(TextView(this@MainActivity).apply {
                layoutParams = LinearLayout.LayoutParams(dpToPx(90), dpToPx(32))
                text = msg.severity
                textSize = 12f
                gravity = Gravity.CENTER
                setTextColor(Color.WHITE)
                background = createRoundedDrawable(severityColor, dpToPx(16))
            })
            addView(topRow)
            addView(textView(formatTimestamp(msg.timestamp), 10f, false).apply {
                setTextColor(Color.parseColor("#888888"))
                setPadding(dpToPx(12), dpToPx(10), dpToPx(12), dpToPx(10))
                setBackgroundColor(Color.parseColor("#1F1B1A"))
            })
            setOnClickListener {
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Детали сообщения")
                    .setMessage("""
                        Хост: ${msg.hostName}
                        Проблема: ${msg.problemName}
                        Важность: ${msg.severity}
                        Сообщение: ${msg.message}
                        Время: ${formatTimestamp(msg.timestamp)}
                    """.trimIndent())
                    .setPositiveButton("OK") { _, _ ->
                        apiClient.markMessageRead(msg.id, object : ZabbixApiClient.Callback<Boolean> {
                            override fun onSuccess(result: Boolean) {
                                loadMessages()
                            }
                            override fun onError(error: String) {
                                Toast.makeText(this@MainActivity, error, Toast.LENGTH_SHORT).show()
                            }
                        })
                    }
                    .show()
            }
        }
    }

    // ========================= Статистика =========================
    private fun displayStatistics() {
        pcsContainer.removeAllViews()
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dpToPx(16), dpToPx(16), dpToPx(16), dpToPx(16)) }
        apiClient.getStats(object : ZabbixApiClient.Callback<ZabbixApiClient.StatsResult> {
            override fun onSuccess(stats: ZabbixApiClient.StatsResult) {
                runOnUiThread {
                    layout.addView(statCard("АКТИВНЫХ ЗАДАЧ", stats.active.toString()))
                    layout.addView(statCard("РЕШЕНО ЗА ДЕНЬ", stats.solvedDay.toString()))
                    layout.addView(statCard("РЕШЕНО ЗА НЕДЕЛЮ", stats.solvedWeek.toString()))
                    layout.addView(statCard("РЕШЕНО ЗА МЕСЯЦ", stats.solvedMonth.toString()))
                    val last = archivedTasks.take(5)
                    if (last.isNotEmpty()) {
                        layout.addView(titleView("ПОСЛЕДНИЕ РЕШЁННЫЕ"))
                        last.forEach { task ->
                            layout.addView(LinearLayout(this@MainActivity).apply {
                                orientation = LinearLayout.VERTICAL
                                background = createRoundedDrawable(Color.parseColor("#331F1B1A"), dpToPx(12))
                                setPadding(dpToPx(12), dpToPx(12), dpToPx(12), dpToPx(12))
                                addView(textView("🔧 ${task.hostName}", 14f, true))
                                addView(textView("⚠️ ${task.triggerName}", 12f, false).apply { setTextColor(Color.parseColor("#AAAAAA")); setPadding(0, dpToPx(4), 0, 0) })
                                addView(textView("Выполнена: ${formatDate(task.completedAt!!)}", 10f, false).apply { setTextColor(Color.parseColor("#888888")); setPadding(0, dpToPx(4), 0, 0) })
                            })
                        }
                    }
                    pcsContainer.addView(layout)
                }
            }
            override fun onError(error: String) {
                runOnUiThread { Toast.makeText(this@MainActivity, error, Toast.LENGTH_SHORT).show() }
            }
        })
    }

    private fun statCard(title: String, value: String) = LinearLayout(this).apply {
        layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { setMargins(0, 0, 0, dpToPx(12)) }
        orientation = LinearLayout.HORIZONTAL
        background = createRoundedDrawable(Color.parseColor("#331F1B1A"), dpToPx(12))
        setPadding(dpToPx(16), dpToPx(16), dpToPx(16), dpToPx(16))
        addView(textView(title, 14f, false).apply { layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f); setTextColor(Color.WHITE) })
        addView(textView(value, 24f, true).apply { setTextColor(Color.parseColor("#CCCCCC")) })
    }

    // ========================= Архив =========================
    private fun displayArchive() {
        pcsContainer.removeAllViews()
        addArchiveFilters()
        displayArchiveTasks()
    }

    private fun addArchiveFilters() {
        val filterLayout = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dpToPx(8), dpToPx(8), dpToPx(8), dpToPx(8))
        }
        val spinner = Spinner(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, dpToPx(40), 1f)
            background = createRoundedDrawable(Color.parseColor("#1F1B1A"), dpToPx(8))
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_item, listOf("Все", "За день", "За неделю", "За месяц", "Диапазон")).apply {
                setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            }
            setSelection(when (archiveFilter) { "day" -> 1; "week" -> 2; "month" -> 3; "range" -> 4 else -> 0 })
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    archiveFilter = when (position) { 1 -> "day"; 2 -> "week"; 3 -> "month"; 4 -> "range" else -> "all" }
                    if (archiveFilter == "range") showDateRangePicker() else displayArchiveTasks()
                }
                override fun onNothingSelected(parent: AdapterView<*>?) {}
            }
        }
        filterLayout.addView(spinner)
        pcsContainer.addView(filterLayout)
    }

    private fun showDateRangePicker() {
        val cal = Calendar.getInstance()
        DatePickerDialog(this, { _, y, m, d ->
            rangeStart = getDateTime(y, m, d, 0, 0)
            DatePickerDialog(this, { _, y2, m2, d2 ->
                rangeEnd = getDateTime(y2, m2, d2, 23, 59)
                displayArchiveTasks()
            }, cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
        }, cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
    }

    private fun getDateTime(y: Int, m: Int, d: Int, h: Int, min: Int): Long {
        val c = Calendar.getInstance()
        c.set(y, m, d, h, min)
        return c.timeInMillis
    }

    private fun displayArchiveTasks() {
        val childCount = pcsContainer.childCount
        if (childCount > 1) pcsContainer.removeViews(1, childCount - 1)
        val filtered = archivedTasks.filter { task ->
            val completed = task.completedAt ?: return@filter false
            when (archiveFilter) {
                "day" -> completed >= System.currentTimeMillis() - TimeUnit.DAYS.toMillis(1)
                "week" -> completed >= System.currentTimeMillis() - TimeUnit.DAYS.toMillis(7)
                "month" -> completed >= System.currentTimeMillis() - TimeUnit.DAYS.toMillis(30)
                "range" -> rangeStart != null && rangeEnd != null && completed in rangeStart!!..rangeEnd!!
                else -> true
            }
        }
        if (filtered.isEmpty()) {
            showEmptyState("Нет задач за выбранный период")
            return
        }
        filtered.forEach { pcsContainer.addView(createTaskCard(it, true)) }
    }

    // ==================== АДМИНКА ====================
    private fun loadUsersForAdmin() {
        apiClient.listUsers(object : ZabbixApiClient.Callback<List<User>> {
            override fun onSuccess(users: List<User>) {
                runOnUiThread {
                    usersList.clear()
                    usersList.addAll(users)
                    displayAdminPanel()
                }
            }
            override fun onError(error: String) {
                runOnUiThread { Toast.makeText(this@MainActivity, error, Toast.LENGTH_LONG).show() }
            }
        })
    }

    private fun displayAdminPanel() {
        pcsContainer.removeAllViews()
        val titleView = TextView(this).apply {
            text = "Управление пользователями"
            textSize = 18f
            setTextColor(Color.WHITE)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(dpToPx(16), dpToPx(16), dpToPx(16), dpToPx(8))
        }
        pcsContainer.addView(titleView)

        val addBtn = Button(this).apply {
            text = "+ Добавить пользователя"
            setBackgroundColor(Color.parseColor("#555555"))
            setTextColor(Color.WHITE)
            setPadding(dpToPx(16), dpToPx(12), dpToPx(16), dpToPx(12))
            setOnClickListener { showAddUserDialog() }
        }
        pcsContainer.addView(addBtn, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            setMargins(dpToPx(16), dpToPx(8), dpToPx(16), dpToPx(8))
        })

        usersRecyclerView = RecyclerView(this).apply {
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            layoutManager = LinearLayoutManager(this@MainActivity)
        }
        userAdapter = UserAdapter(usersList, object : UserAdapter.OnUserActionListener {
            override fun onEdit(user: User) { showEditUserDialog(user) }
            override fun onDelete(user: User) { confirmDelete(user) }
        })
        usersRecyclerView.adapter = userAdapter
        pcsContainer.addView(usersRecyclerView)
    }

    private fun showAddUserDialog() {
        val dialogView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dpToPx(20), dpToPx(20), dpToPx(20), dpToPx(20))
        }
        val usernameInput = EditText(this).apply { hint = "Логин" }
        val passwordInput = EditText(this).apply {
            hint = "Пароль"
            inputType = android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val roleSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_item, listOf("user", "admin")).apply {
                setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            }
        }
        dialogView.addView(usernameInput)
        dialogView.addView(passwordInput)
        dialogView.addView(roleSpinner)
        AlertDialog.Builder(this)
            .setTitle("Добавить пользователя")
            .setView(dialogView)
            .setPositiveButton("Добавить") { _, _ ->
                val username = usernameInput.text.toString().trim()
                val password = passwordInput.text.toString()
                val role = if (roleSpinner.selectedItemPosition == 1) "admin" else "user"
                if (username.isNotEmpty() && password.isNotEmpty()) {
                    apiClient.createUser(username, password, role, object : ZabbixApiClient.Callback<Boolean> {
                        override fun onSuccess(result: Boolean) { loadUsersForAdmin() }
                        override fun onError(error: String) {
                            Toast.makeText(this@MainActivity, error, Toast.LENGTH_SHORT).show()
                        }
                    })
                } else {
                    Toast.makeText(this@MainActivity, "Заполните все поля", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Отмена", null)
            .show()
    }

    private fun showEditUserDialog(user: User) {
        val dialogView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dpToPx(20), dpToPx(20), dpToPx(20), dpToPx(20))
        }
        val roleSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_item, listOf("user", "admin")).apply {
                setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            }
            setSelection(if (user.role == "admin") 1 else 0)
        }
        val newPasswordInput = EditText(this).apply {
            hint = "Новый пароль (оставьте пустым, чтобы не менять)"
            inputType = android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        dialogView.addView(TextView(this).apply { text = "Роль:" })
        dialogView.addView(roleSpinner)
        dialogView.addView(newPasswordInput)
        AlertDialog.Builder(this)
            .setTitle("Редактировать ${user.username}")
            .setView(dialogView)
            .setPositiveButton("Сохранить") { _, _ ->
                val newRole = if (roleSpinner.selectedItemPosition == 1) "admin" else "user"
                val newPassword = newPasswordInput.text.toString().ifEmpty { null }
                apiClient.updateUser(user.id, newRole, newPassword, object : ZabbixApiClient.Callback<Boolean> {
                    override fun onSuccess(result: Boolean) { loadUsersForAdmin() }
                    override fun onError(error: String) {
                        Toast.makeText(this@MainActivity, error, Toast.LENGTH_SHORT).show()
                    }
                })
            }
            .setNegativeButton("Отмена", null)
            .show()
    }

    private fun confirmDelete(user: User) {
        AlertDialog.Builder(this)
            .setTitle("Удалить пользователя")
            .setMessage("Удалить ${user.username}?")
            .setPositiveButton("Удалить") { _, _ ->
                apiClient.deleteUser(user.id, object : ZabbixApiClient.Callback<Boolean> {
                    override fun onSuccess(result: Boolean) { loadUsersForAdmin() }
                    override fun onError(error: String) {
                        Toast.makeText(this@MainActivity, error, Toast.LENGTH_SHORT).show()
                    }
                })
            }
            .setNegativeButton("Отмена", null)
            .show()
    }

    // ========================= Вспомогательные методы =========================
    private fun getStatusEmoji(severity: String): String = when (severity.lowercase()) {
        "высокая", "high", "disaster" -> "🔴"
        "средняя", "average" -> "🟡"
        "низкая", "warning" -> "🔵"
        else -> "📨"
    }

    private fun formatTimestamp(timestamp: String): String {
        return try {
            val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
            val utcDate = sdf.parse(timestamp) ?: return timestamp
            val mskTime = Date(utcDate.time + 3 * 60 * 60 * 1000)
            val diff = Date().time - mskTime.time
            val minutes = TimeUnit.MILLISECONDS.toMinutes(diff)
            when {
                minutes < 1 -> "Только что"
                minutes < 60 -> "$minutes мин назад"
                minutes < 1440 -> "${minutes / 60} ч назад"
                else -> SimpleDateFormat("dd.MM HH:mm", Locale.getDefault()).format(mskTime)
            }
        } catch (e: Exception) { timestamp }
    }

    private fun formatDate(ts: Long): String = SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()).format(Date(ts))

    private fun getSeverityColor(severity: String): Int = when (severity.lowercase()) {
        "высокая", "high", "disaster" -> Color.parseColor("#F44336")
        "средняя", "average" -> Color.parseColor("#FF9800")
        "низкая", "warning" -> Color.parseColor("#FFC107")
        else -> Color.parseColor("#888888")
    }

    private fun textView(text: String, size: Float, bold: Boolean) = TextView(this).apply {
        this.text = text
        textSize = size
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private fun titleView(text: String) = textView(text, 14f, true).apply {
        setTextColor(Color.parseColor("#CCCCCC"))
        setPadding(dpToPx(12), dpToPx(12), dpToPx(12), dpToPx(4))
    }

    private fun showEmptyState(msg: String) {
        pcsContainer.addView(textView(msg, 16f, false).apply {
            gravity = Gravity.CENTER
            setTextColor(Color.GRAY)
            setPadding(dpToPx(16), dpToPx(32), dpToPx(16), dpToPx(32))
        })
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), PERMISSION_REQUEST_CODE)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(NOTIFICATION_CHANNEL_ID, "Уведомления Zabbix", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Уведомления о новых сообщениях от Zabbix"
                enableVibration(true)
            }
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
        }
    }

    private fun getStatusBarHeight(): Int {
        val resourceId = resources.getIdentifier("status_bar_height", "dimen", "android")
        return if (resourceId > 0) resources.getDimensionPixelSize(resourceId) else 0
    }

    private fun getNavigationBarHeight(): Int {
        val resourceId = resources.getIdentifier("navigation_bar_height", "dimen", "android")
        return if (resourceId > 0) resources.getDimensionPixelSize(resourceId) else 0
    }

    private fun dpToPx(dp: Int): Int = (dp * resources.displayMetrics.density).toInt()
    private fun createRoundedDrawable(color: Int, radius: Int): GradientDrawable = GradientDrawable().apply { setColor(color); cornerRadius = radius.toFloat() }

    // ========================= ПОСТРОЕНИЕ ГЛАВНОГО ЭКРАНА =========================
    private fun showMainScreen() {
        // ... (ваша огромная вёрстка, я её сохраняю, но для краткости оставляю как есть)
        // Вставьте сюда ваш метод showMainScreen() из оригинального проекта.
        // Поскольку он очень длинный, я не копирую его повторно, но вы его уже имеете.
        // Важно, чтобы он работал и вызывал loadTasks() и loadMessages() при переключении вкладок.
        // В вашем оригинале в конце showMainScreen() вызывается displayActiveTasks() – это нормально.
    }

    data class TabConfig(val iconName: String, val index: Int, val iconSizeDp: Int, val offsetY: Int, val offsetX: Int)

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacksAndMessages(null)
    }
}
