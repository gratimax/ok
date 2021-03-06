import collections
import csv
from functools import wraps
from io import StringIO

from flask import (Blueprint, render_template, flash, redirect, Response,
                   url_for, abort, request, stream_with_context)
from werkzeug.exceptions import BadRequest

from flask_login import current_user
import pygal
from pygal.style import CleanStyle

from server.autograder import autograde_assignment, submit_continous
from server.controllers.auth import get_token_if_valid

import server.controllers.api as ok_api
from server.models import (User, Course, Assignment, Enrollment, Version,
                           GradingTask, Backup, Score, Group, db)
from server.constants import STAFF_ROLES, STUDENT_ROLE, GRADE_TAGS
from server.extensions import cache
import server.forms as forms
import server.highlight as highlight
import server.utils as utils


admin = Blueprint('admin', __name__)

def is_staff(course_arg=None):
    """ A decorator for routes to ensure that user is a member of
    the course staff.

    Usage:
    @is_staff() - A staff member for any course
    @is_staff(course_arg=1) A staff member for the course with id 1
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if current_user.is_authenticated:
                if current_user.is_admin:
                    return func(*args, **kwargs)
                roles = current_user.enrollments(roles=STAFF_ROLES)
                if len(roles) > 0:
                    if course_arg:
                        course = kwargs[course_arg]
                        if course in [r.course.id for r in roles]:
                            return func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)
            else:
                return redirect(url_for("student.index"))
            flash("You are not on the course staff", "error")
            return redirect(url_for("student.index"))
        return wrapper
    return decorator


def get_courses(cid=None):
    #  TODO : The decorator could add these to the routes
    if current_user.is_authenticated and current_user.is_admin:
        courses = Course.query.all()
    else:
        enrollments = current_user.enrollments(roles=STAFF_ROLES)
        courses = [e.course for e in enrollments]
    if not cid:
        return courses, []

    matching_courses = [c for c in courses if c.id == cid]
    if len(matching_courses) == 0:
        abort(401)  # TODO to actual error page
    current_course = matching_courses[0]
    return courses, current_course


@admin.route("/")
@is_staff()
def index():
    courses, current_course = get_courses()
    if courses:
        return redirect(url_for(".course_assignments", cid=courses[0].id))
    return render_template('staff/index.html', courses=courses)

@admin.route('/grading')
@is_staff()
def grading_tasks(username=None):
    courses, current_course = get_courses()
    page = request.args.get('page', 1, type=int)
    tasks_query = GradingTask.query.filter_by(grader=current_user)
    queue = (tasks_query.options(db.joinedload('assignment'))
                        .order_by(GradingTask.score_id.asc())
                        .order_by(GradingTask.created.asc())
                        .paginate(page=page, per_page=20))

    remaining = tasks_query.filter_by(score_id=None).count()
    percent_left = (1-(remaining/max(1, queue.total))) * 100
    return render_template('staff/grading/queue.html', courses=courses,
                           queue=queue, remaining=remaining,
                           percent_left=percent_left)

def grading_view(backup, form=None):
    """ General purpose grading view. Used by routes."""
    courses, current_course = get_courses()
    assign = backup.assignment
    diff_type = request.args.get('diff', None)
    if diff_type not in (None, 'short', 'full'):
        diff_type = None
    if not assign.files and diff_type:
        diff_type = None

    # sort comments by (filename, line)
    comments = collections.defaultdict(list)
    for comment in backup.comments:
        comments[(comment.filename, comment.line)].append(comment)

    # highlight files and add comments
    files = highlight.diff_files(assign.files, backup.files(), diff_type)
    for filename, lines in files.items():
        for line in lines:
            line.comments = comments[(filename, line.line_after)]

    group = [User.query.get(o) for o in backup.owners()]
    scores = [s for s in backup.scores if not s.archived]
    task = backup.grading_tasks
    if task:
        # Choose the first grading_task
        task = task[0]

    return render_template(
        'staff/grading/code.html', courses=courses, assignment=assign,
        backup=backup, group=group, scores=scores, files=files,
        diff_type=diff_type, task=task, form=form
    )

@admin.route('/grading/<hashid:bid>')
@is_staff()
def grading(bid):
    backup = Backup.query.get(bid)
    if not (backup and Backup.can(backup, current_user, "grade")):
        abort(404)

    form = forms.GradeForm()
    existing = Score.query.filter_by(backup=backup).first()

    if existing and existing.kind in GRADE_TAGS:
        form = forms.GradeForm(kind=existing.kind)
        form.kind.data = existing.kind
        form.message.data = existing.message
        form.score.data = existing.score

    return grading_view(backup, form=form)

@admin.route('/composition/<hashid:bid>')
@is_staff()
def composition(bid):
    backup = Backup.query.get(bid)
    if not (backup and Backup.can(backup, current_user, "grade")):
        abort(404)
    form = forms.CompositionScoreForm()
    existing = Score.query.filter_by(backup=backup, kind="composition").first()
    if existing:
        form.kind.data = "composition"
        form.message.data = existing.message
        form.score.data = existing.score
    return grading_view(backup, form=form)

@admin.route('/grading/<hashid:bid>/grade', methods=['POST'])
@is_staff()
def grade(bid):
    """ Used as a form submission endpoint. """
    backup = Backup.query.options(db.joinedload('assignment')).get(bid)
    if not backup:
        abort(404)
    if not Backup.can(backup, current_user, 'grade'):
        flash("You do not have permission to score this assignment.", "warning")
        abort(401)

    form = forms.GradeForm()
    score_kind = form.kind.data.strip().lower()
    is_composition = (score_kind == "composition")
    # TODO: Form should include redirect url instead of guessing based off tag

    if is_composition:
        form = forms.CompositionScoreForm()

    if not form.validate_on_submit():
        return grading_view(backup, form=form)

    score = Score(backup=backup, grader=current_user,
                  assignment_id=backup.assignment_id)
    form.populate_obj(score)
    db.session.add(score)
    db.session.commit()

    # Archive old scores of the same kind
    score.archive_duplicates()

    next_page = None
    flash_msg = "Added a {0} {1} score.".format(score.score, score_kind)

    # Find GradingTasks applicable to this score
    tasks = backup.grading_tasks
    for task in tasks:
        task.score = score
        cache.delete_memoized(User.num_grading_tasks, task.grader)

    db.session.commit()

    if len(tasks) == 1:
        # Go to next task for the current task queue if possible.
        task = tasks[0]
        next_task = task.get_next_task()
        next_route = '.composition' if is_composition else '.grading'
        # Handle case when the task is on the users queue
        if next_task:
            flash_msg += (" There are {0} tasks left. Here's the next submission:"
                          .format(task.remaining))
            next_page = url_for(next_route, bid=next_task.backup_id)
        else:
            flash_msg += " All done with grading for {}".format(backup.assignment.name)
            next_page = url_for('.grading_tasks')
    else:
        # TODO: Send task id or redirect_url in the grading form
        # For now, default to grading tasks
        next_page = url_for('.grading_tasks')

    flash(flash_msg, 'success')

    if not next_page:
        next_page = url_for('.assignment_queues', aid=backup.assignment_id,
                            cid=backup.assignment.course_id)
    return redirect(next_page)


@admin.route("/client/<name>", methods=['GET', 'POST'])
@is_staff()
def client_version(name):
    courses, current_course = get_courses()

    version = Version.query.filter_by(name=name).one_or_none()
    if not version:
        version = Version(name=name)
    form = forms.VersionForm(obj=version)
    if form.validate_on_submit():
        form.populate_obj(version)

        db.session.add(version)
        db.session.commit()

        cache.delete_memoized(Version.get_current_version, name)
        cache.delete_memoized(ok_api.Version.get)

        flash(name + " version updated successfully.", "success")
        return redirect(url_for(".client_version", name=name))

    return render_template('staff/client_version.html',
                           courses=courses, current_course=current_course,
                           version=version, form=form)


@admin.route("/course/<int:cid>")
@is_staff(course_arg='cid')
def course(cid):
    return redirect(url_for(".course_assignments", cid=cid))
    # courses, current_course = get_courses(cid)
    # return render_template('staff/course/index.html',
    #                       courses=courses, current_course=current_course)


@admin.route("/course/<int:cid>/assignments")
@is_staff(course_arg='cid')
def course_assignments(cid):
    courses, current_course = get_courses(cid)
    assgns = current_course.assignments
    active_asgns = [a for a in assgns if a.active]
    due_asgns = [a for a in assgns if not a.active]
    # TODO CLEANUP : Better way to send this data to the template.
    return render_template('staff/course/assignments.html',
                           courses=courses, current_course=current_course,
                           active_asgns=active_asgns, due_assgns=due_asgns)


@admin.route("/course/<int:cid>/assignments/new", methods=["GET", "POST"])
@is_staff(course_arg='cid')
def new_assignment(cid):
    courses, current_course = get_courses(cid)
    if not Assignment.can(None, current_user, 'create'):
        flash('Insufficient permissions', 'error')
        return abort(401)

    form = forms.AssignmentForm(course=current_course)
    if form.validate_on_submit():
        model = Assignment(course_id=cid, creator_id=current_user.id)
        form.populate_obj(model)
        db.session.add(model)
        db.session.commit()
        cache.delete_memoized(Assignment.name_to_assign_info)

        flash("Assignment created successfully.", "success")
        return redirect(url_for(".course_assignments", cid=cid))

    return render_template('staff/course/assignment.new.html', form=form,
                           courses=courses, current_course=current_course)

@admin.route("/course/<int:cid>/assignments/<int:aid>",
             methods=['GET', 'POST'])
@is_staff(course_arg='cid')
def assignment(cid, aid):
    courses, current_course = get_courses(cid)
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign:
        return abort(404)
    if not Assignment.can(assign, current_user, 'edit'):
        flash('Insufficient permissions', 'error')
        return abort(401)

    form = forms.AssignmentUpdateForm(obj=assign, course=current_course)
    stats = Assignment.assignment_stats(assign.id)

    if form.validate_on_submit():
        # populate_obj converts back to UTC
        form.populate_obj(assign)
        assign.creator_id = current_user.id
        cache.delete_memoized(Assignment.name_to_assign_info)
        db.session.commit()
        flash("Assignment edited successfully.", "success")

    return render_template('staff/course/assignment.html', assignment=assign,
                           form=form, courses=courses, stats=stats,
                           current_course=current_course)

@admin.route("/course/<int:cid>/assignments/<int:aid>/stats")
@is_staff(course_arg='cid')
def assignment_stats(cid, aid):
    courses, current_course = get_courses(cid)
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not Assignment.can(assign, current_user, 'edit'):
        flash('Insufficient permissions', 'error')
        return abort(401)
    stats = Assignment.assignment_stats(assign.id, detailed=True)

    pie_chart = pygal.Pie(half_pie=True, disable_xml_declaration=True,
                          style=CleanStyle,
                          inner_radius=.5, legend_at_bottom=True)
    pie_chart.title = 'Students submission status'
    pie_chart.add('Students with Submissions', stats['students_submitted'])
    pie_chart.add('Not Submitted', stats['students_nosubmit'])

    return render_template('staff/course/assignment.stats.html',
                           assignment=assign, subm_chart=pie_chart,
                           courses=courses, stats=stats,
                           current_course=current_course)

@admin.route("/course/<int:cid>/assignments/<int:aid>/template",
             methods=['GET', 'POST'])
@is_staff(course_arg='cid')
def templates(cid, aid):
    courses, current_course = get_courses(cid)
    assignment = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not Assignment.can(assignment, current_user, 'edit'):
        flash('Insufficient permissions', 'error')
        return abort(401)

    form = forms.AssignmentTemplateForm()

    if assignment.course != current_course:
        return abort(401)

    if form.validate_on_submit():
        files = request.files.getlist("template_files")
        if files:
            templates = {}
            for template in files:
                templates[template.filename] = str(template.read(), 'latin1')
            assignment.files = templates
        cache.delete_memoized(Assignment.name_to_assign_info)
        db.session.commit()
        flash("Templates Uploaded", "success")

    # TODO: Use same student facing code rendering/highlighting
    return render_template('staff/course/assignment.template.html',
                           assignment=assignment, form=form, courses=courses,
                           current_course=current_course)

@admin.route("/course/<int:cid>/assignments/<int:aid>/scores")
@is_staff(course_arg='cid')
def export_scores(cid, aid):
    courses, current_course = get_courses(cid)
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not Assignment.can(assign, current_user, 'export'):
        flash('Insufficient permissions', 'error')
        return abort(401)
    query = (Score.query.options(db.joinedload('backup'))
                  .filter_by(assignment=assign, archived=False))

    custom_items = ('time', 'is_late', 'email', 'group')
    items = custom_items + Enrollment.export_items + Score.export_items

    def generate_csv():
        """ Generate csv export of scores for assignment.
        Num Queries: ~2N queries for N scores.
        """
        # Yield Column Info as first row
        yield ','.join(items) + '\n'
        for score in query:
            csv_file = StringIO()
            csv_writer = csv.DictWriter(csv_file, fieldnames=items)
            submitters = score.backup.enrollment_info()
            group = [s.user.email for s in submitters]
            time_str = utils.local_time(score.backup.created, course)
            for submitter in submitters:
                data = {'email': submitter.user.email,
                        'time': time_str,
                        'is_late': score.backup.is_late,
                        'group': group}
                data.update(submitter.export)
                data.update(score.export)
                csv_writer.writerow(data)
            yield csv_file.getvalue()

    file_name = "{0}.csv".format(assign.name.replace('/', '-'))
    disposition = 'attachment; filename={0}'.format(file_name)

    # TODO: Remove. For local performance testing.
    # return render_template('staff/index.html', data=list(generate_csv()))
    return Response(stream_with_context(generate_csv()), mimetype='text/csv',
                    headers={'Content-Disposition': disposition})

@admin.route("/course/<int:cid>/assignments/<int:aid>/queues")
@is_staff(course_arg='cid')
def assignment_queues(cid, aid):
    courses, current_course = get_courses(cid)
    assignment = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not Assignment.can(assignment, current_user, 'grade'):
        flash('Insufficient permissions', 'error')
        return abort(401)

    queues = GradingTask.get_staff_tasks(assignment.id)

    incomplete = [q.grader.email for q in queues if q.completed != q.total]
    complete = [q.grader.email for q in queues if q.completed == q.total]

    mailto_link = "mailto://{0}?subject={1}&body={2}&cc={3}".format(
        current_user.email,
        "{0} grading queue is not finished".format(assignment.display_name),
        "Queue Link: {0}".format(url_for('admin.grading_tasks', _external=True)),
        ','.join(incomplete)
    )

    remaining = len(incomplete)
    percent_left = (1-(remaining/max(1, len(queues)))) * 100

    if current_user.email in incomplete:
        flash("Hmm... You aren't finished with your queue.", 'info')
    elif current_user.email in complete:
        flash("Nice! You are all done with your queue", 'success')
    else:
        flash("You don't have a queue for this assignment", 'info')

    return render_template('staff/grading/overview.html', courses=courses,
                           current_course=current_course,
                           assignment=assignment, queues=queues,
                           incomplete=incomplete, mailto=mailto_link,
                           remaining=remaining, percent_left=percent_left)

@admin.route("/course/<int:cid>/assignments/<int:aid>/queues/<int:uid>")
@is_staff(course_arg='cid')
def assignment_single_queue(cid, aid, uid):
    courses, current_course = get_courses(cid)
    assignment = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not Assignment.can(assignment, current_user, 'grade'):
        flash('Insufficient permissions', 'error')
        return abort(401)

    assigned_grader = User.get_by_id(uid)
    if not Assignment.can(assignment, assigned_grader, 'grade'):
        return abort(404)

    page = request.args.get('page', 1, type=int)
    tasks_query = GradingTask.query.filter_by(assignment=assignment,
                                              grader_id=uid)
    queue = (tasks_query.options(db.joinedload('assignment'))
                        .order_by(GradingTask.score_id.asc())
                        .order_by(GradingTask.created.asc())
                        .paginate(page=page, per_page=20))

    remaining = tasks_query.filter_by(score_id=None).count()
    percent_left = (1-(remaining/max(1, queue.total))) * 100

    return render_template('staff/grading/queue.html', courses=courses,
                           current_course=current_course,
                           assignment=assignment, grader=assigned_grader,
                           queue=queue, remaining=remaining,
                           percent_left=percent_left)


@admin.route("/course/<int:cid>/assignments/<int:aid>/queues/new",
             methods=["GET", "POST"])
@is_staff(course_arg='cid')
def assign_grading(cid, aid):
    courses, current_course = get_courses(cid)
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign or not Assignment.can(assign, current_user, 'grade'):
        flash('Cannot access assignment', 'error')
        return abort(404)

    form = forms.CreateTaskForm()
    course_staff = sorted(current_course.get_staff(), key=lambda x: x.role)
    details = lambda e: "{0} - ({1})".format(e.user.email, e.role)
    form.staff.choices = [(utils.encode_id(e.user_id), details(e))
                          for e in course_staff]

    if not form.staff.data:
        # Select all by default
        form.staff.default = [u[0] for u in form.staff.choices]
        form.process()

    if form.validate_on_submit():
        # TODO: Use worker job for this (this is query intensive)
        selected_users = []
        for hash_id in form.staff.data:
            user = User.get_by_id(utils.decode_id(hash_id))
            if user and user.is_enrolled(cid, roles=STAFF_ROLES):
                selected_users.append(user)

        # Available backups:
        students, backups, no_submissions = assign.course_submissions()

        tasks = GradingTask.create_staff_tasks(backups, selected_users, aid, cid,
                                               form.kind.data, form.only_unassigned.data)

        num_with_submissions = len(students) - len(no_submissions)
        flash(("Created {0} tasks ({1} students) for {2} staff."
               .format(len(tasks), num_with_submissions, len(selected_users))),
              "success")
        return redirect(url_for('.assignment', cid=cid, aid=aid))

    # Return template with options for who has to grade.
    return render_template('staff/grading/assign_tasks.html',
                           current_course=current_course, assignment=assign,
                           form=form)

@admin.route("/course/<int:cid>/assignments/<int:aid>/autograde",
             methods=["GET", "POST"])
@is_staff(course_arg='cid')
def autograde(cid, aid):
    courses, current_course = get_courses(cid)
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign or not Assignment.can(assign, current_user, 'grade'):
        flash('Cannot access assignment', 'error')
        return abort(404)
    auth_token = get_token_if_valid()
    form = forms.AutogradeForm()
    if form.validate_on_submit():
        if hasattr(form, 'token') and form.token.data:
            token = form.token.data
        else:
            token = auth_token

        autopromotion = form.autopromote.data
        try:
            autograde_assignment(assign, form.autograder_id.data,
                                 token, autopromotion=autopromotion)
            flash('Submitted to the autograder', 'success')
        except ValueError as e:
            flash(str(e), 'error')

    if not form.token.data and auth_token:
        form.token.data = auth_token[0]

    if not form.autograder_id.data and assign.autograding_key:
        form.autograder_id.data = assign.autograding_key

    return render_template('staff/grading/autograde.html',
                           current_course=current_course,
                           assignment=assign, form=form)

@admin.route("/course/<int:cid>/enrollment", methods=['GET', 'POST'])
@is_staff(course_arg='cid')
def enrollment(cid):
    courses, current_course = get_courses(cid)
    single_form = forms.EnrollmentForm(prefix="single")
    if single_form.validate_on_submit():
        email, role = single_form.email.data, single_form.role.data
        Enrollment.enroll_from_form(cid, single_form)
        flash("Added {email} as {role}".format(
            email=email, role=role), "success")

    students = (Enrollment.query.options(db.joinedload('user'))
                .filter_by(course_id=cid, role=STUDENT_ROLE)
                .order_by(Enrollment.created.desc())
                .all())

    staff = (Enrollment.query.options(db.joinedload('user'))
             .filter(Enrollment.course_id == cid, Enrollment.role.in_(STAFF_ROLES))
             .all())

    return render_template('staff/course/enrollment.html',
                           enrollments=students, staff=staff,
                           single_form=single_form,
                           courses=courses,
                           current_course=current_course)

@admin.route("/course/<int:cid>/enrollment/batch",
             methods=['GET', 'POST'])
@is_staff(course_arg='cid')
def batch_enroll(cid):
    courses, current_course = get_courses(cid)
    batch_form = forms.BatchEnrollmentForm()
    if batch_form.validate_on_submit():
        new, updated = Enrollment.enroll_from_csv(cid, batch_form)
        msg = ("Added {new}, Updated {old} {role} enrollments"
               .format(new=new, role=batch_form.role.data, old=updated))
        flash(msg, "success")
        return redirect(url_for(".enrollment", cid=cid))

    return render_template('staff/course/enrollment.batch.html',
                           batch_form=batch_form,
                           courses=courses,
                           current_course=current_course)

@admin.route("/course/<int:cid>/enrollment/csv")
@is_staff(course_arg='cid')
def enrollment_csv(cid):
    courses, current_course = get_courses(cid)

    query = (Enrollment.query.options(db.joinedload('user'))
                       .filter_by(course_id=cid, role=STUDENT_ROLE))

    file_name = "{0}-roster.csv".format(current_course.offering.replace('/', '-'))
    disposition = 'attachment; filename={0}'.format(file_name)
    items = User.export_items + Enrollment.export_items

    def row_to_csv(row):
        return [row.export, row.user.export]

    csv_generator = utils.generate_csv(query, items, row_to_csv)

    return Response(stream_with_context(csv_generator),
                    mimetype='text/csv',
                    headers={'Content-Disposition': disposition})


################
# Student View #
################

@admin.route("/course/<int:cid>/<string:email>")
@is_staff(course_arg='cid')
def student_view(cid, email):
    courses, current_course = get_courses(cid)
    assignments = current_course.assignments

    student = User.lookup(email)
    if not student:
        abort(404)

    enrollment = student.is_enrolled(cid)
    if not enrollment:
        flash("This email is not enrolled", 'warning')

    assignments = {
        'active': [a.user_status(student) for a in assignments
                   if a.active],
        'inactive': [a.user_status(student) for a in assignments
                     if not a.active]
    }

    return render_template('staff/student/overview.html',
                           courses=courses, current_course=current_course,
                           student=student, enrollment=enrollment,
                           assignments=assignments)

@admin.route("/course/<int:cid>/<string:email>/<int:aid>")
@is_staff(course_arg='cid')
def student_assignment_detail(cid, email, aid):
    courses, current_course = get_courses(cid)
    page = request.args.get('page', 1, type=int)

    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign or not Assignment.can(assign, current_user, 'grade'):
        flash('Cannot access assignment', 'error')
        return abort(404)

    student = User.lookup(email)
    if not student.is_enrolled(cid):
        flash("This user is not enrolled", 'warning')

    assignment_stats = assign.user_status(student)

    user_ids = assign.active_user_ids(student.id)

    latest = assignment_stats.final_subm or assign.backups(user_ids).first()

    stats = {
        'num_backups': assign.backups(user_ids).count(),
        'num_submissions': assign.submissions(user_ids).count(),
        'current_q': None,
        'attempts': None,
        'latest': latest,
        'analytics': latest and latest.analytics()
    }

    backups = (Backup.query.options(db.joinedload('scores'),
                                    db.joinedload('submitter'))
                     .filter(Backup.submitter_id.in_(user_ids),
                             Backup.assignment_id == assign.id)
                     .order_by(Backup.flagged.desc(), Backup.submit.desc(),
                               Backup.created.desc()))

    paginate = backups.paginate(page=page, per_page=15)

    if stats['analytics']:
        stats['current_q'] = stats['analytics'].get('question')
        stats['attempts'] = (stats['analytics'].get('history', {})
                                               .get('all_attempts'))

    return render_template('staff/student/assignment.html',
                           courses=courses, current_course=current_course,
                           student=student, assignment=assign,
                           add_member_form=forms.StaffAddGroupFrom(),
                           paginate=paginate,
                           csrf_form=forms.CSRFForm(),
                           upload_form=forms.UploadSubmissionForm(),
                           stats=stats,
                           assign_status=assignment_stats)

########################
# Student view actions #
########################

@admin.route("/course/<int:cid>/<string:email>/<int:aid>/add_member",
             methods=["POST"])
@is_staff(course_arg='cid')
def staff_group_add(cid, email, aid):
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign or not Assignment.can(assign, current_user, 'grade'):
        flash('Cannot access assignment', 'error')
        return abort(404)

    form = forms.StaffAddGroupFrom()
    result_page = url_for('.student_assignment_detail', cid=cid,
                          email=email, aid=aid)

    student = User.lookup(email)
    if not student:
        return abort(404)

    if form.validate_on_submit():
        target = User.lookup(form.email.data)
        if not target or not target.is_enrolled(cid):
            flash("This user is not enrolled", 'warning')
            return redirect(result_page)
        try:
            Group.force_add(current_user, student, target, assign)
        except BadRequest as e:
            flash("Error: {}".format(str(e.description)), 'error')
            return redirect(result_page)

    return redirect(result_page)

@admin.route("/course/<int:cid>/<string:email>/<int:aid>/remove_member",
             methods=["POST"])
@is_staff(course_arg='cid')
def staff_group_remove(cid, email, aid):
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign or not Assignment.can(assign, current_user, 'grade'):
        return abort(404)

    student = User.lookup(email)
    if not student:
        abort(404)

    result_page = url_for('.student_assignment_detail', cid=cid,
                          email=email, aid=aid)

    form = forms.CSRFForm()
    if form.validate_on_submit():
        target = User.lookup(request.form['target'])
        if not target:
            flash('{} does not exist'.format(request.form['target']), 'error')
            return redirect(result_page)
        try:
            Group.force_remove(current_user, student, target, assign)
        except BadRequest as e:
            flash("Error: {}".format(str(e.description)), 'error')
    return redirect(result_page)

@admin.route("/course/<int:cid>/<string:email>/<int:aid>/flag",
             methods=["POST"])
@is_staff(course_arg='cid')
def staff_flag_backup(cid, email, aid):
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign or not Assignment.can(assign, current_user, 'grade'):
        return abort(404)
    result_page = url_for('.student_assignment_detail', cid=cid,
                          email=email, aid=aid)

    student = User.lookup(email)
    if not student:
        abort(404)
    user_ids = assign.active_user_ids(student.id)

    bid = request.form.get('bid')

    form = forms.CSRFForm()
    if form.validate_on_submit():
        backup = Backup.query.filter_by(id=utils.decode_id(bid),
                                        assignment=assign).one_or_none()
        if not backup:
            flash('{} does not exist'.format(bid, 'error'))
            return redirect(result_page)

        if not backup.flagged:
            result = assign.flag(backup.id, user_ids)
            flash('Flagged backup {} for grading'.format(bid), 'success')
        else:
            result = assign.unflag(backup.id, user_ids)
            flash('Removed grading flag on {}'.format(bid), 'success')

    return redirect(result_page)


@admin.route("/course/<int:cid>/<string:email>/<int:aid>/submit",
             methods=["POST"])
@is_staff(course_arg='cid')
def staff_submit_backup(cid, email, aid):
    assign = Assignment.query.filter_by(id=aid, course_id=cid).one_or_none()
    if not assign or not Assignment.can(assign, current_user, 'grade'):
        return abort(404)
    result_page = url_for('.student_assignment_detail', cid=cid,
                          email=email, aid=aid)
    student = User.lookup(email)
    if not student:
        abort(404)
    user_ids = assign.active_user_ids(student.id)
    # TODO: DRY - Unify with student upload code - should just be a function
    form = forms.UploadSubmissionForm()
    if form.validate_on_submit():
        files = request.files.getlist("upload_files")
        if files:
            templates = assign.files
            messages = {'file_contents': {}}
            for upload in files:
                data = upload.read()
                if len(data) > 2097152:
                    # File is too large (over 2 MB)
                    flash(("{} is over the maximum file size limit of 2MB"
                           .format(upload.filename)),
                          'danger')
                    return redirect(result_page)
                messages['file_contents'][upload.filename] = str(data, 'latin1')
            if templates:
                missing = []
                for template in templates:
                    if template not in messages['file_contents']:
                        missing.append(template)
                if missing:
                    flash(("Missing files: {}. The following files are required: {}"
                           .format(', '.join(missing), ', '.join([t for t in templates]))
                           ), 'danger')
                    return redirect(result_page)
            # use student, not current_user
            backup = ok_api.make_backup(student, assign.id, messages, True)
            if form.flag_submission.data:
                assign.flag(backup.id, user_ids)
            if assign.autograding_key:
                try:
                    submit_continous(backup)
                except ValueError as e:
                    flash('Did not send to autograder: {}'.format(e), 'warning')

            flash("Uploaded submission (ID: {})".format(backup.hashid), 'success')
            return redirect(result_page)
